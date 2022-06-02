#!/usr/bin/env python3

import time
import os
import time
import csv
import eyed3
import argparse
import youtube_dl
import spotipy
import spotipy.util as util
import asyncio
from concurrent.futures import ThreadPoolExecutor
from unidecode import unidecode


def get_songs_from_csvfile(csvfile, args):
    songs = []
    with open(csvfile, 'r') as csvfile:
        reader = csv.reader(csvfile)
        next(reader)  # Skip the first line
        if args.skip:
            print('Skipping', args.skip, 'songs')
            for i in range(args.skip):
                next(reader)
        for row in reader:
            songs.append({
                'name': unidecode(row[0]).strip(),
                'artist': unidecode(row[1]).strip(),
                'album': unidecode(row[2]).strip()
            })
    return songs


class MyLogger(object):
    def debug(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        print(msg)


def download_finish(d):
    if d['status'] == 'finished':
        print('\x1b[1A\x1b[2K')
        print("\x1b[1A[\033[93mConverting\033[00m] %s" % d['filename'])


def download_song(song, folder):
    probable_filename = folder + '/' + song['name'] + ' - ' + \
        song['artist'] + '.mp3'
    if os.path.isfile(probable_filename):
        # The file may already be there, so skip
        print('[\033[93mSkipping\033[00m] %s by %s' % \
            (song['name'], song['artist']))
        return
    opts = {
        'format': 'bestaudio/best',
        'forcejson': True,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '256',
        }],
 #       'verbose': True,
        'progress_hooks': [download_finish],
        'logger': MyLogger(),
        'outtmpl': folder + '/' + song['name'] + ' - ' + song['artist'] + '.%(ext)s'
    }
    url = ' '.join([song['name'], song['artist'], 'audio', 'youtube'])
    url = 'ytsearch:' + url
    print('[\033[91mFetching\033[00m] %s' % probable_filename)
    with youtube_dl.YoutubeDL(opts) as ydl:
        ydl.download([url])
    if os.path.isfile(probable_filename):
        afile = eyed3.load(probable_filename)
        afile.tag.title = song['name']
        afile.tag.artist = song['artist']
        afile.tag.album = song['album']
        afile.tag.save()
    else:
        print('\x1b[1A\x1b[2K')
        print('\x1b[1A[\033[91mMetadata\033[00m] Could not set metadata for %s\nTemp' % \
            probable_filename)

    print('\x1b[1A\x1b[2K')
    print('\x1b[1A[\033[92mDownloaded]\033[00m', song['name'], '-', song['artist'])

def force_download_song(song, folder):
    tries = 20
    while tries > 0:
        try:
            download_song(song, folder)
            return
        except (spotipy.exceptions.SpotifyException, youtube_dl.utils.DownloadError, Exception):
            print('\x1b[1A\x1b[2K')
            print('[\033[91mFAILED\033[00m] Could not download %s Trying again' % song)
            time.sleep(3)
        tries -= 1
    print('[\033[91mFAILED\033[00m] Could not download %s. Gave up.' % song)



async def download_songs(songs, folder):
    futures = []
    executor = ThreadPoolExecutor(max_workers=20)
    loop = asyncio.get_event_loop()
    print(f"Songs: {len(songs)}\n")
    for song in songs:
        print(f"Adding: {song}\n")
        future = loop.run_in_executor(executor, force_download_song, song, folder)
        futures.append(future)

    await asyncio.sleep(4)
    res = await asyncio.gather(*futures)


def get_songs_from_playlist(tracks, args):
    songs = []
    print(f"tracks: {len(tracks)}")
    for item in tracks[args.skip:]:
        track = item['track']
        songs.append({
            'name': unidecode(track['name']).strip(),
            'artist': unidecode(track['artists'][0]['name']).strip(),
            'album': unidecode(track['album']['name']).strip()
        })
    return songs


def get_all_tracks(sp, username, playlist_id):
    tracks = []
    limit = 100
    offset = 0

    while True:
        new_tracks = sp.user_playlist_tracks(
            username,
            playlist_id,
            limit=limit,
            offset=offset,
        )['items']
        if len(new_tracks) == 0:
            break
        tracks.extend(new_tracks)
        offset = offset + len(new_tracks)
    return tracks



def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-f', '--folder', help="keep the files in the folder specified")
    parser.add_argument('-c', '--create', help="try to create folder if doesn't exist",
                        action="store_true")
    parser.add_argument('--skip', help="number of songs to skip from the start of csv",
                        type=int)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-csv', help="input csv file")
    group.add_argument('-username', help="username of your spotify account")

    args = parser.parse_args()

    # getting current working directory
    folder = os.path.dirname(os.path.realpath(__file__))

    loop = asyncio.get_event_loop()

    if args.folder:
        if os.path.isdir(args.folder):
            folder = os.path.abspath(args.folder)
        elif args.create:
            try:
                os.makedirs(args.folder)
                folder = os.path.abspath(args.folder)
            except e:
                print('Error while creating folder')
                raise
        else:
            print('No such folder. Aborting..')
            exit()
        print('Storing files in', folder)
    if args.csv:
        if os.path.isfile(args.csv):
            csvfile = args.csv
            songs = get_songs_from_csvfile(csvfile, args)
            loop.create_task(download_songs(songs, folder))
        else:
            print('No such csv file. Aborting..')
            exit()

    if args.username:
        scope = 'playlist-read playlist-read-private'
        token = util.prompt_for_user_token(args.username, scope)
        if token:
            sp = spotipy.Spotify(auth=token)
            try:
                playlists = sp.user_playlists(args.username)
            except spotipy.client.SpotifyException:
                print("Invalid Username")
                exit()
            if len(playlists) > 0:
                print("All Playlists: ")
                for index, playlist in enumerate(playlists['items']):
                    print(str(index + 1) + ": " + playlist['name'])
                n = input("Enter S.N. of playlists (seprated by comma): ").split(",")
                if n:
                    for i in range(0, len(n), 2):
                       playlist_folder = folder+"/"+playlists['items'][int(n[i]) - 1]['name']
                       print('Storing files in', playlist_folder)
                       if not os.path.isdir(playlist_folder):
                            try:
                                os.makedirs(playlist_folder )
                            except e:
                                print('Error while creating folder')
                                raise
                       playlist_id = playlists['items'][int(n[i]) - 1]['id']
                       tracks = get_all_tracks(sp, args.username, playlist_id)
                       songs = get_songs_from_playlist(tracks, args)
                       loop.create_task(download_songs(songs, playlist_folder))
                else:
                    print("No S.N. Provided! Aborting...")
            else:
                print("No Playlist Found!")
        else:
            print("Can't get token for", username)
            exit()

    loop.run_forever()
    loop.close()

if __name__ == '__main__':
    main()
