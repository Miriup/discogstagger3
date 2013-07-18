#!/usr/bin/python
# -*- coding: utf-8 -*-
import os
import errno
import shutil
import logging
import sys
import imghdr
import glob
import ConfigParser
from optparse import OptionParser
from ext.mediafile import MediaFile
from discogstagger.taggerutils import (
    TaggerUtils,
    create_nfo,
    create_m3u,
    get_images)
from discogstagger.tagger_config import TaggerConfig

import os, errno

# !TODO move this to taggerutils - this class should handle basically the whole
# logic, not in here
def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as exc: # Python >2.5
        if exc.errno == errno.EEXIST and os.path.isdir(path):
            pass
        else: raise

p = OptionParser()
p.add_option("-r", "--releaseid", action="store", dest="releaseid",
             help="The discogs.com release id of the target album")
p.add_option("-s", "--source", action="store", dest="sdir",
             help="The directory that you wish to tag")
p.add_option("-d", "--destination", action="store", dest="destdir",
             help="The (base) directory to copy the tagged files to")
p.add_option("-c", "--conf", action="store", dest="conffile",
             help="The discogstagger configuration file.")

p.set_defaults(conffile="/etc/discogstagger/discogs_tagger.conf")
(options, args) = p.parse_args()

if not options.sdir or not os.path.exists(options.sdir):
    p.error("Please specify a valid source directory ('-s')")

tagger_config = TaggerConfig()
tagger_config.read(options.conffile)
config = tagger_config.config

logging.basicConfig(level=config.getint("logging", "level"))
logger = logging.getLogger(__name__)

# read necessary config options for batch processing
id_file = config.get("batch", "id_file")
dir_format_batch = "dir"
dir_format = None

# read tags from batch file if available
tagger_config.read(os.path.join(options.sdir, id_file))

if config.get("source", "id"):
    releaseid = config.get("source", "id").strip()

# command line parameter overwrites config parameter in file
if options.releaseid:
    releaseid = options.releaseid

if not releaseid:
    p.error("Please specify the discogs.com releaseid ('-r')")

# read destination directory
if not options.destdir:
    destdir = options.sdir
else:
    destdir = options.destdir
    logger.info("destdir set to %s", options.destdir)

logger.info("Using destination directory: %s", destdir)

# some config options, which are not "overwritable" through release-tags
keep_original = config.getboolean("details", "keep_original")
embed_coverart = config.getboolean("details", "embed_coverart")
use_lower_filenames = config.getboolean("details", "use_lower_filenames")
use_folder_jpg = config.getboolean("details", "use_folder_jpg")
copy_other_files = config.getboolean("details", "copy_other_files")

user_agent = config.get("common", "user-agent")

# config options "overwritable" through release-tags
keep_tags = config.get("details", "keep_tags")

enocder_tag = None
encoder_tag = config.get("tags", "encoder")

use_style = config.getboolean("details", "use_style")
split_discs_folder = config.getboolean("details", "split_discs_folder")
split_discs = config.getboolean("details", "split_discs")
if split_discs:
    split_discs_extension = config.get("details", "split_discs_extension").strip('"')
split_artists = config.get("details", "split_artists").strip('"')
split_genres_and_styles = config.get("details", "split_genres_and_styles").strip('"')

release = TaggerUtils(options.sdir, destdir, releaseid, config)
release.disc_folder_name = disc_folder_name
release.group_name = group_name

first_image_name = "folder.jpg"

if not use_folder_jpg:
    first_image_name = images_format + "-01.jpg"

# ensure we were able to map the release appropriately.
if not release.tag_map:
    logger.error("Unable to match file list to discogs release '%s'" %
                  releaseid)
    sys.exit()

#
# start tagging actions. --> put this out of here into its own object
#
artist = split_artists.join(release.album.artists)
artist = release.album.clean_name(artist)

logger.info("Tagging album '%s - %s'" % (artist, release.album.title))

dest_dir_name = release.dest_dir_name

if os.path.exists(dest_dir_name):
    logger.error("Destination already exists %s" % dest_dir_name)
    sys.exit("%s directory already exists, aborting." % dest_dir_name)
else:
    logger.info("Creating destination directory '%s'" % dest_dir_name)
    mkdir_p(dest_dir_name)

logger.info("Downloading and storing images")
get_images(release.album.images, dest_dir_name, images_format, first_image_name)

# !TODO remove all the following stuff, should be done in the taggerutils (rename
# to taghandler?) or in a new class, this wrapper should just provide all needed
# information for the real tagging and thats it.

disc_names = dict()
folder_names = dict()
if release.album.disctotal > 1 and split_discs_folder:
    logger.debug("Creating disc structure")
    for i in range(1, release.album.disctotal + 1):
        folder_name = "%s%.d" % (release.album_folder_name, i)
        disc_dir_name = os.path.join(dest_dir_name, folder_name)
        mkdir_p(disc_dir_name)
#This is duplicate, remove one of the following statements
        disc_names[i] = disc_dir_name
        folder_names[i] = folder_name
else:
    folder_names[1] = ""
#        # copy only if necessary (on request) - otherwise attach original
#        for filename in glob.glob(os.path.join(dest_dir_name, '*.jpg')):
#            shutil.copy(filename, disc_dir_name)
#    # delete only on request
#    for filename in glob.glob(os.path.join(dest_dir_name, '*.jpg')):
#        os.remove(os.path.join(dest_dir_name, filename))

for track in release.tag_map:
    # copy old file into new location
    if release.album.disctotal > 1 and split_discs_folder:
        target_folder = disc_names[int(track.discnumber)]
    else:
        target_folder = dest_dir_name

    logger.debug("Source file %s" % os.path.join(options.sdir,
                 track.orig_file))
    logger.info("Writing file %s" % os.path.join(target_folder, track.new_file))
    logger.debug("metadata -> %.2d %s - %s" % (track.tracknumber, track.artist,
                 track.title))
    logger.debug("----------> %s" % track.new_file)

    shutil.copyfile(track.orig_file,
                    os.path.join(target_folder, track.new_file))

    # load metadata information
    metadata = MediaFile(os.path.join(target_folder, track.new_file))

    # read already existing (and still wanted) properties
    keepTags = {}
    for name in keep_tags.split(","):
        if getattr(metadata, name):
            keepTags[name] = getattr(metadata, name)

    # remove current metadata
    metadata.delete()

    # set album metadata
    metadata.album = release.album.title

    if split_discs_folder and release.album.disctotal > 1:
        # the fileext should be stored on the album/track as well
        fileext = os.path.splitext(track.orig_file)[1]
        disc_title_extension = release._value_from_tag_format(split_discs_extension, 
            track.tracknumber, track.position - 1, fileext)
        metadata.album = "%s%s" % (metadata.album, disc_title_extension)

    metadata.composer = artist
    metadata.albumartist = artist
    metadata.albumartist_sort = release.album.sort_artist
    metadata.label = release.album.label
    metadata.year = release.album.year
    metadata.country = release.album.country
    metadata.url = release.album.url
    # add styles to the grouping tag (right now, we can just use one)
    metadata.grouping = release.album.styles

    # adding two as there is no standard. discogstagger pre v1
    # used (TXXX desc="Catalog #")
    # mediafile uses TXXX desc="CATALOGNUMBER"
    metadata.catalognum = release.album.catno
    metadata.catalognumber = release.album.catno

    # use the correct genre field, on config use the first style
    genre = release.album.genres
    if use_style:
        genre = release.album.style

    metadata.genre = genre
    metadata.discogs_id = releaseid

    if release.album.disctotal and release.album.disctotal > 1 and track.discnumber:
        logger.info("writing disctotal and discnumber")
        metadata.disc = track.discnumber
        metadata.disctotal = release.album.disctotal

    if release.album.is_compilation:
        metadata.comp = True

    metadata.comments = release.album.note

    # encoder
    if encoder_tag is not None:
        metadata.encoder = encoder_tag

#    if track.discsubtotal:
#        metadata.discsubtotal = track.discsubtotal

    # set track metadata
    metadata.title = track.title
    metadata.artist = track.artist
    metadata.artist_sort = track.sortartist
    metadata.track = track.tracknumber

    # the following value will be wrong, if the disc has a name or is a multi
    # disc release --> fix it
    metadata.tracktotal = release.album.tracktotal_on_disc(track.discnumber)


    # it does not make sense to store this in the "common" configuration, but only in the 
    # id.txt. we use a special naming convention --> most probably we should reuse the 
    # configuration parser for this one as well, no?
    for name, value in release_tags.items():
        if name.startswith("tag:"):
            name = name.split(":")
            name = name[1]
            setattr(metadata, name, value)

    first_image_name = release.first_image_name
# this should be done in a cleaner way to avoid multiple images in different
# folders (use the dest_dir again....)
    if embed_coverart and os.path.exists(os.path.join(dest_dir_name,
                                         first_image_name)):
        imgdata = open(os.path.join(dest_dir_name,
                       first_image_name)).read()
        imgtype = imghdr.what(None, imgdata)

        if imgtype in ("jpeg", "png"):
            logger.info("Embedding album art.")
            metadata.art = imgdata

    if not keepTags is None:
        for name in keepTags:
            setattr(metadata, name, keepTags[name])

    metadata.save()

#
# start supplementary actions
#
# adopt for multi disc support (copy to disc folder, add disc number, ...)
logger.info("Generating .nfo file")
create_nfo(release.album.album_info, dest_dir_name, release.nfo_filename)

# adopt for multi disc support
logger.info("Generating .m3u file")
create_m3u(release.tag_map, folder_names, dest_dir_name, release.m3u_filename)

# copy "other files" on request
if copy_other_files and len(release.copy_files) > 0:
    logger.info("copying files from source directory")
    copy_files = release.copy_files
    dir_list = os.listdir(options.sdir)
    logger.debug("start_dir: %s" % options.sdir)
    logger.debug("dir list: %s" % dir_list)
    file_list = [os.path.join(options.sdir, x) for x in dir_list if not x.lower().endswith(TaggerUtils.FILE_TYPE) 
                                        and os.path.isfile(os.path.join(options.sdir, x))]
    copy_files.extend(file_list)

    for fname in copy_files:
        if not fname.endswith(".m3u"):
            logger.debug("source: %s" % fname)
            logger.debug("target: %s" % os.path.join(dest_dir_name, os.path.basename(fname)))
            shutil.copyfile(fname, os.path.join(dest_dir_name, os.path.basename(fname)))

# remove source directory, if configured as such.
if not keep_original:
    logger.info("Deleting source directory '%s'" % options.sdir)
    shutil.rmtree(options.sdir)



logger.info("Tagging complete.")
