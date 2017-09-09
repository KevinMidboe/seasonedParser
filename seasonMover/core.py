#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# @Author: KevinMidboe
# @Date:   2017-08-25 23:22:27
# @Last Modified by:   KevinMidboe
# @Last Modified time: 2017-09-09 14:57:54

from guessit import guessit
import os, errno
import logging
import tvdb_api

from video import VIDEO_EXTENSIONS, Episode, Movie, Video
from subtitle import SUBTITLE_EXTENSIONS, Subtitle, get_subtitle_path

logger = logging.getLogger(__name__)


#: Supported archive extensions
ARCHIVE_EXTENSIONS = ('.rar',)

@profile
def scan_video(path):
    """Scan a video from a `path`.

    :param str path: existing path to the video.
    :return: the scanned video.
    :rtype: :class:`~subliminal.video.Video`

    """
    # check for non-existing path
    if not os.path.exists(path):
        raise ValueError('Path does not exist')

    # check video extension
    # if not path.endswith(VIDEO_EXTENSIONS):
    #     raise ValueError('%r is not a valid video extension' % os.path.splitext(path)[1])

    dirpath, filename = os.path.split(path)
    logger.info('Scanning video %r in %r', filename, dirpath)

    # guess
    parent_path = path.strip(filename)
    # video = Video.fromguess(filename, parent_path, guessit(path))
    video = Video('test')
    # guessit(path)

    return video


def scan_subtitle(path):
   if not os.path.exists(path):
      raise ValueError('Path does not exist')

   dirpath, filename = os.path.split(path)
   logger.info('Scanning video %r in %r', filename, dirpath)

   # guess
   parent_path = path.strip(filename)
   subtitle = Subtitle.fromguess(filename, parent_path, guessit(path))


   return subtitle


@profile
def scan_files(path, age=None, archives=True):
    """Scan `path` for videos and their subtitles.

    See :func:`refine` to find additional information for the video.

    :param str path: existing directory path to scan.
    :param datetime.timedelta age: maximum age of the video or archive.
    :param bool archives: scan videos in archives.
    :return: the scanned videos.
    :rtype: list of :class:`~subliminal.video.Video`

    """
    # check for non-existing path
    if not os.path.exists(path):
        raise ValueError('Path does not exist')

    # check for non-directory path
    if not os.path.isdir(path):
        raise ValueError('Path is not a directory')

    # walk the path
    mediafiles = []
    for dirpath, dirnames, filenames in os.walk(path):
        logger.debug('Walking directory %r', dirpath)

        # remove badly encoded and hidden dirnames
        for dirname in list(dirnames):
            if dirname.startswith('.'):
                logger.debug('Skipping hidden dirname %r in %r', dirname, dirpath)
                dirnames.remove(dirname)

        # scan for videos
        for filename in filenames:
            # filter on videos and archives
            if not (filename.endswith(VIDEO_EXTENSIONS) or filename.endswith(SUBTITLE_EXTENSIONS) or archives and filename.endswith(ARCHIVE_EXTENSIONS)):
                continue

            # skip hidden files
            if filename.startswith('.'):
                logger.debug('Skipping hidden filename %r in %r', filename, dirpath)
                continue

            # reconstruct the file path
            filepath = os.path.join(dirpath, filename)

            # skip links
            if os.path.islink(filepath):
                logger.debug('Skipping link %r in %r', filename, dirpath)
                continue

            # skip old files
            if age and datetime.utcnow() - datetime.utcfromtimestamp(os.path.getmtime(filepath)) > age:
                logger.debug('Skipping old file %r in %r', filename, dirpath)
                continue

            # scan
            if filename.endswith(VIDEO_EXTENSIONS):  # video
                try:
                    video = scan_video(filepath)
                    mediafiles.append(video)
                except ValueError:  # pragma: no cover
                    logger.exception('Error scanning video')
                    continue
            elif archives and filename.endswith(ARCHIVE_EXTENSIONS):  # archive
                try:
                    video = scan_archive(filepath)
                    mediafiles.append(video)
                except (NotRarFile, RarCannotExec, ValueError):  # pragma: no cover
                    logger.exception('Error scanning archive')
                    continue
            elif filename.endswith(SUBTITLE_EXTENSIONS): # subtitle
               try:
                  subtitle = scan_subtitle(filepath)
                  mediafiles.append(subtitle)
               except ValueError: 
                  logger.exception('Error scanning subtitle')
                  continue
            else:  # pragma: no cover
                raise ValueError('Unsupported file %r' % filename)


    return mediafiles


@profile
def organize_files(path):
   hashList = {}
   mediafiles = scan_files(path)
   print(mediafiles)

   for file in mediafiles:
        hashList.setdefault(file.__hash__(),[]).append(file)
         # hashList[file.__hash__()] = file

   return hashList


def save_subtitles(files, single=False, directory=None, encoding=None):
    t = tvdb_api.Tvdb()

    if not isinstance(files, list):
        files = [files]

    for file in files:
        # TODO this should not be done in the loop
        dirname = "%s S%sE%s" % (file.series, "%02d" % (file.season), "%02d" % (file.episode))

        createParentfolder = not dirname in file.parent_path
        if createParentfolder:
            dirname = os.path.join(file.parent_path, dirname)
            print('Created: %s' % dirname)
            try:
                os.makedirs(dirname)
            except OSError as e:
                if e.errno != errno.EEXIST:
                    raise

        # TODO Clean this !
        try:
            tvdb_episode = t[file.series][file.season][file.episode]
            episode_title = tvdb_episode['episodename']
        except:
            episode_title = ''

        old = os.path.join(file.parent_path, file.name)

        if file.name.endswith(SUBTITLE_EXTENSIONS):
            lang = file.getLanguage()
            sdh = '.sdh' if file.sdh else ''
            filename = "%s S%sE%s %s%s.%s.%s" % (file.series, "%02d" % (file.season), "%02d" % (file.episode), episode_title, sdh, lang, file.container)
        else:
            filename = "%s S%sE%s %s.%s" % (file.series, "%02d" % (file.season), "%02d" % (file.episode), episode_title, file.container)

        if createParentfolder:
            newname = os.path.join(dirname, filename)
        else:
            newname = os.path.join(file.parent_path, filename)

        
        print('Moved: %s ---> %s' % (old, newname))
        os.rename(old, newname)

        print()


    # for hash in files:
    #   hashIndex = [files[hash]]
    #   for hashItems in hashIndex:
    #      for file in hashItems:
    #         print(file.series)

    # saved_subtitles = []
    # for subtitle in files:
    #     # check content
    #     if subtitle.name is None:
    #         logger.error('Skipping subtitle %r: no content', subtitle)
    #         continue

    #     # check language
    #     if subtitle.language in set(s.language for s in saved_subtitles):
    #         logger.debug('Skipping subtitle %r: language already saved', subtitle)
    #         continue

    #     # create subtitle path
    #     subtitle_path = get_subtitle_path(video.name, None if single else subtitle.language)
    #     if directory is not None:
    #         subtitle_path = os.path.join(directory, os.path.split(subtitle_path)[1])

    #     # save content as is or in the specified encoding
    #     logger.info('Saving %r to %r', subtitle, subtitle_path)
    #     if encoding is None:
    #         with io.open(subtitle_path, 'wb') as f:
    #             f.write(subtitle.content)
    #     else:
    #         with io.open(subtitle_path, 'w', encoding=encoding) as f:
    #             f.write(subtitle.text)
    #     saved_subtitles.append(subtitle)

    #     # check single
    #     if single:
    #         break

    # return saved_subtitles


def main():
   episodePath = '/Volumes/media/tv/Black Mirror/Black Mirror Season 01/'

   t = tvdb_api.Tvdb()

   hashList = organize_files(episodePath)
   pprint(hashList)



if __name__ == '__main__':
    main()