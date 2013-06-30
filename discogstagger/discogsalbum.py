import logging
import re

import discogs_client as discogs

from album import Album, Disc, Track

logger = logging.getLogger(__name__)

class DiscogsAlbum(object):
    """ Wraps the discogs-client-api script, abstracting the minimal set of
        artist data required to tag an album/release

        >>> from discogstagger.discogsalbum import DiscogsAlbum
        >>> release = DiscogsAlbum(40522) # fetch discogs release id 40522
        >>> print "%s - %s (%s / %s)" % (release.artist, release.title, release.catno,
        >>> release.label)

        Blunted Dummies - House For All (12DEF006 / Definitive Recordings)

        >>> for song in release.tracks: print "[ %.2d ] %s - %s" % (song.position,
        >>> song.artist, song.title)

        [ 01 ] Blunted Dummies - House For All (Original Mix)
        [ 02 ] Blunted Dummies - House For All (House 4 All Robots Mix)
        [ 03 ] Blunted Dummies - House For All (Eddie Richard's Mix)
        [ 04 ] Blunted Dummies - House For All (J. Acquaviva's Mix)
        [ 05 ] Blunted Dummies - House For All (Ruby Fruit Jungle Mix) """

    def __init__(self, releaseid):
        discogs.user_agent = "discogstagger +http://github.com/jesseward"
        self.release = discogs.Release(releaseid)

    def map(self):
        """ map the retrieved information to the tagger specific objects """

        album = Album(self.release._id, self.release.title, self.artists)

        album.sort_artist = self.sort_artist(self.release.artists)
        album.url = self.url
        album.catnumbers = [catno for name, catno in self.labels_and_numbers]
        album.labels = [name for name, catno in self.labels_and_numbers]
        album.images = self.images
        album.year = self.year
        album.genres = self.release.data["genres"]
        album.styles = self.release.data["styles"]
        album.year = self.release.data["country"]
        if "notes" in self.release.data:
            album.notes = self.release.data["notes"]
        album.disctotal = self.disctotal
        album.is_compilation = self.is_compilation

        self.discs_and_tracks

        return album


    @property
    def album_info(self):
        """ Dumps the release data to a formatted text string. Formatted for
            .nfo file  """

        logger.debug("Writing nfo file")
        div = "_ _______________________________________________ _ _\n"
        r = div
        r += "  Name : %s - %s\n" % (self.artist, self.title)
        r += " Label : %s\n" % (self.label)
        r += " Genre : %s\n" % (self.genre)
        r += " Catno : %s\n" % (self.catno)
        r += "  Year : %s\n" % (self.year)
        r += "   URL : %s\n" % (self.url)

        if self.master_id:
            r += "Master : http://www.discogs.com/master/%s\n" % self.master_id

        r += div
        for song in self.tracks:
            r += "%.2d. %s - %s\n" % (song.position, song.artist, song.title)
        return r

    @property
    def url(self):
        """ returns the discogs url of this release """

        return "http://www.discogs.com/release/%s" % self.release._id

    @property
    def labels_and_numbers(self):
        """ Returns all available catalog numbers"""
        for label in self.release.data["labels"]:
            yield self.clean_duplicate_handling(label["name"]), label["catno"]

    @property
    def images(self):
        """ return a single list of images for the given album """

        try:
            return [x["uri"] for x in self.release.data["images"]]
        except KeyError:
            pass

    @property
    def year(self):
        """ returns the album release year obtained from API 2.0 """

        good_year = re.compile("\d\d\d\d")
        try:
            return good_year.match(str(self.release.data["year"])).group(0)
        except IndexError:
            return "1900"

    @property
    def disctotal(self):
        return int(self.release.data["formats"][0]["qty"])

    @property
    def master_id(self):
        """ returns the master release id """

        try:
            return self.release.data["master_id"]
        except KeyError:
            return None

    def _gen_artist(self, artist_data):
        """ yields a list of artists name properties """
        for x in artist_data:
            yield x.name

    @property
    def artists(self):
        """ obtain the album artists (normalized using clean_name). """
        artists = []
        for name in self._gen_artist(self.release.artists):
            artists.append(self.clean_name(name))

        return artists

    def sort_artist(self, artist_data):
        """ Obtain a clean sort artist """
        return self.clean_duplicate_handling(artist_data[0].name)

#    @property
#    def artist(self):
#        """ obtain the album artist """
#
#        rel_artist = self.split_artists.join(self._gen_artist(self.release.artists))
#        return self.clean_name(rel_artist)

    def disc_and_track_no(self, position):
        """ obtain the disc and tracknumber from given position """
        idx = position.find("-")
        if idx == -1:
            idx = position.find(".")
        if idx == -1:
            idx = 0
        tracknumber = position[idx + 1:]
        discnumber = position[:idx]

        return {'tracknumber': tracknumber, 'discnumber': discnumber}

    def tracktotal_on_disc(self, discnumber):
        logger.info("discs: %s" % self.discs)
        return self.discs[discnumber]

    @property
    def is_compilation(self):
        if self.release.data["artists"][0]["name"] == "Various":
            return True

        for format in self.release.data["formats"]:
            if "descriptions" in format:
                for description in format["descriptions"]:
                    if description == "compilation":
                        return True

        return False

    @property
    def tracks(self):
        """ provides the tracklist of the given release id """

        track_list = []
        discsubtitle = None
        for i, t in enumerate((x for x in self.release.tracklist
                              if x["type"] == "Track")):
# this is pretty much the same as the artist stuff in the album,
# try to refactor it
            try:
                sort_artist = self.clean_name(t["artists"][0].name)
                artist = self._gen_artist(t["artists"])
#                artist = self.clean_name(artist)
            except IndexError:
                artist = self.artist
                sort_artist = self.sort_artist

            track = TrackContainer()

            # on multiple discs there do appears a subtitle as the first "track"
            # on the cd in discogs, this seems to be wrong, but we would like to
            # handle it anyway
            if t["title"] and not t["position"] and not t["duration"]:
                discsubtitle = t["title"]
                continue

            track.position = i + 1

            if self.disctotal > 1:
                pos = self.disc_and_track_no(t["position"])
                track.tracknumber = int(pos["tracknumber"])
                track.discnumber = int(pos["discnumber"])
            else:
                track.tracknumber = int(t["position"])
                track.discnumber = 1
            self.discs[int(track.discnumber)] = int(track.tracknumber)

            if discsubtitle:
                track.discsubtitle = discsubtitle

            track.sortartist = sort_artist
            track.artist = artist

            track.title = t["title"]
            track_list.append(track)

        return track_list

    @property
    def discs_and_tracks(self):
        """ provides the tracklist of the given release id """

        disc_list = []
        track_list = []
        discsubtitle = None
        disc = Disc(1)
        for i, t in enumerate((x for x in self.release.tracklist
                              if x["type"] == "Track")):
# this is pretty much the same as the artist stuff in the album,
# try to refactor it
            try:
                sort_artist = self.clean_name(t["artists"][0].name)
                artist = self._gen_artist(t["artists"])
#                artist = self.clean_name(artist)
            except IndexError:
                artist = self.artist
                sort_artist = self.sort_artist

            track = Track(i + 1, artist, t["title"])

            # on multiple discs there do appears a subtitle as the first "track"
            # on the cd in discogs, this seems to be wrong, but we would like to
            # handle it anyway
            if t["title"] and not t["position"] and not t["duration"]:
                discsubtitle = t["title"]
                continue

            track.position = i + 1

            if self.disctotal > 1:
                pos = self.disc_and_track_no(t["position"])
                track.tracknumber = int(pos["tracknumber"])
                track.discnumber = int(pos["discnumber"])
            else:
                track.tracknumber = int(t["position"])
                track.discnumber = 1
#            self.discs[int(track.discnumber)] = int(track.tracknumber)

            if discsubtitle:
                track.discsubtitle = discsubtitle

            track.sortartist = sort_artist
            track.artist = artist

            track_list.append(track)

        return track_list

    def clean_duplicate_handling(self, clean_target):
        """ remove discogs duplicate handling eg : John (1) """
        return re.sub("\s\(\d+\)", "", clean_target)

    def clean_name(self, clean_target):
        """ Cleans up the format of the artist or label name provided by
            Discogs.
            Examples:
                'Goldie (12)' becomes 'Goldie'
                  or
                'Aphex Twin, The' becomes 'The Aphex Twin'
            Accepts a string to clean, returns a cleansed version """

        groups = {
            "(.*),\sThe$": "The",
        }

        clean_target = self.clean_duplicate_handling(clean_target)

        for regex in groups:
            if re.search(r"%s" % regex, clean_target):
                clean_target = "%s %s" % (groups[regex],
                                          re.search("%s" % regex,
                                          clean_target).group(1))
        return clean_target
