#!/usr/bin/env python3.6
# -*- coding: utf-8 -*-
# @Author: KevinMidboe
# @Date:   2017-08-25 23:22:27
# @Last Modified by:   KevinMidboe
# @Last Modified time: 2017-09-29 12:35:24

from guessit import guessit
from babelfish import Language, LanguageReverseError
from hashids import Hashids
import os, errno
import logging
import tvdb_api
import click
from pprint import pprint

import env_variables as env

from video import VIDEO_EXTENSIONS, Episode, Movie, Video
from subtitle import SUBTITLE_EXTENSIONS, Subtitle, get_subtitle_path
from utils import sanitize, refine

logging.basicConfig(filename=env.logfile, level=logging.INFO)


def search_external_subtitles(path, directory=None):
    dirpath, filename = os.path.split(path)
    dirpath = dirpath or '.'
    fileroot, fileext = os.path.splitext(filename)

    subtitles = {}
    for p in os.listdir(directory or dirpath):
        if not p.endswith(SUBTITLE_EXTENSIONS):
            continue

        language = Language('und')
        language_code = p[len(fileroot):-len(os.path.splitext(p)[1])].replace(fileext, '').replace('_','-')[1:]
        if language_code:
            try:
                language = Language.fromietf(language_code)
            except (ValueError, LanguageReverseError):
                logging.error('Cannot parse language code %r', language_code)

        subtitles[p] = language
    logging.debug('Found subtitles %r', subtitles)

    return subtitles

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
    if not path.endswith(VIDEO_EXTENSIONS):
        raise ValueError('%r is not a valid video extension' % os.path.splitext(path)[1])

    dirpath, filename = os.path.split(path)
    logging.info('Scanning video %r in %r', filename, dirpath)

    # guess
    video = Video.fromguess(path, guessit(path))

    # size
    video.size = os.path.getsize(path)

    # hash of name
    hashids = Hashids(min_length=16)
    if isinstance(v, Episode):
        videoHash = hashids.encode(''.join(self.title, self.year or ''))
    elif isinstance(v, Movie):
        videoHash = hashids.encode(''.join(self.series, self.season, self.episode))
    video.hash = videoHash

    return video


def scan_subtitle(path):
   if not os.path.exists(path):
      raise ValueError('Path does not exist')

   dirpath, filename = os.path.split(path)
   logging.info('Scanning subtitle %r in %r', filename, dirpath)

   # guess
   parent_path = path.strip(filename)
   subtitle = Subtitle.fromguess(parent_path, guessit(path))


   return subtitle


def scan_videos(path):
    """Scan `path` for videos and their subtitles.

    See :func:`refine` to find additional information for the video.

    :param str path: existing directory path to scan.
    :return: the scanned videos.
    :rtype: list of :class:`~subliminal.video.Video`

    """
    # check for non-existing path
    if not os.path.exists(path):
        raise ValueError('Path does not exist')

    # check for non-directory path
    if not os.path.isdir(path):
        raise ValueError('Path is not a directory')

    # setup progress bar
    path_children = 0
    for _ in os.walk(path): path_children += 1
    with click.progressbar(length=path_children, show_pos=True, label='Searching folders for videos') as bar:

        # walk the path
        videos = []
        for dirpath, dirnames, filenames in os.walk(path):
            logging.debug('Walking directory %r', dirpath)

            # remove badly encoded and hidden dirnames
            for dirname in list(dirnames):
                if dirname.startswith('.'):
                    logging.debug('Skipping hidden dirname %r in %r', dirname, dirpath)
                    dirnames.remove(dirname)

            # scan for videos
            for filename in filenames:
                # filter on videos and archives
                if not (filename.endswith(VIDEO_EXTENSIONS)):
                    logging.debug('Skipping non-video file %s', filename)
                    continue

                # skip hidden files
                if filename.startswith('.'):
                    logging.debug('Skipping hidden filename %r in %r', filename, dirpath)
                    continue

                # reconstruct the file path
                filepath = os.path.join(dirpath, filename)

                # skip links
                if os.path.islink(filepath):
                    logging.debug('Skipping link %r in %r', filename, dirpath)
                    continue

                # scan
                if filename.endswith(VIDEO_EXTENSIONS):  # video
                    try:
                        video = scan_video(filepath)
                    except ValueError:  # pragma: no cover
                        logging.exception('Error scanning video')
                        continue
                else:  # pragma: no cover
                    raise ValueError('Unsupported file %r' % filename)

                videos.append(video)

            bar.update(1)

        return videos


def organize_files(path):
   hashList = {}
   mediafiles = scan_files(path)
   # print(mediafiles)

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

def scan_folder(path):
    videos = []
    ignored_videos = []
    errored_paths = []
    logging.debug('Collecting path %s', path)

    # non-existing
    if not os.path.exists(path):
        try:
            video = Video.fromname(path)
        except:
            logging.exception('Unexpected error while collecting non-existing path %s', path)
            errored_paths.append(path)

        video.subtitle_languages |= set(search_external_subtitles(video.name, directory=path).values())
        
        refine(video)
        videos.append(video)
        # Increment bar to full ?

    # directories
    if os.path.isdir(path):
        try:
            scanned_videos = scan_videos(path)
        except:
            logging.exception('Unexpected error while collecting directory path %s', path)
            errored_paths.append(path)

        # Iterates over our scanned videos
        with click.progressbar(scanned_videos, label='Parsing videos') as bar:
            for v in bar:
                v.subtitle_languages |= set(search_external_subtitles(v.name,
                                                                          directory=path).values())
                refine(v)
                videos.append(v)

    click.echo('%s video%s collected / %s error%s' % (
        click.style(str(len(videos)), bold=True, fg='green' if videos else None),
        's' if len(videos) > 1 else '',
        click.style(str(len(errored_paths)), bold=True, fg='red' if errored_paths else None),
        's' if len(errored_paths) > 1 else '',
    ))

    return videos

def pickforgirlscouts(video):
    if isinstance(video, Movie):
        if video.title != None and video.year != None:
            return True

    elif isinstance(video, Episode):
        if video.series != None and video.season != None and video.episode != None and type(video.episode) != list:
            return True

    return False

def main():
    path = '/mnt/rescue/'

    videos = scan_folder(path)

    scout = []
    civilan = []
    for video in videos:
        girl = pickforgirlscouts(video)
        if girl:
            scout.append(girl)
        else:
            civilan.append(girl)

    click.echo('%s scouts%s collected / %s civilans%s' % (
        click.style(str(len(scout)), bold=True, fg='green' if scout else None),
        's' if len(scout) > 1 else '',
        click.style(str(len(civilan)), bold=True, fg='red' if civilan else None),
        's' if len(civilan) > 1 else '',
    ))


if __name__ == '__main__':
    main()

