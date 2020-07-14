#!/usr/bin/env python3

import configparser
import os
import typing

import pandas
import tweepy

CREDENTIALS_FILE = "credentials.ini"
PROGRESS_FILE = "last_row.txt"
IMAGE_TEMPLATE = "output/{tlid}.png"

# wrapper around tweet functionality
def tweet(api: tweepy.API,
          message: str,
          image_paths: typing.List[str] = [],
          reply_to_status: typing.Optional[tweepy.models.Status] = None,
          dry_run: bool = False) -> typing.Optional[tweepy.models.Status]:
    tweet_kwargs = {}

    print("")

    # upload images
    if (len(image_paths) > 0):
        media_ids = []
        for image_path in image_paths:
            if (dry_run):
                print("Not uploading: %s" % image_path)
            else:
                print("Uploading: %s" % image_path)
                media_ids.append(api.media_upload(image_path).media_id)
        tweet_kwargs["media_ids"] = media_ids

    # reply
    if (reply_to_status):
        tweet_kwargs["in_reply_to_status_id"] = reply_to_status.id
        message = "@bariexplorer %s" % message
        print("Set in_reply_to_status_id to %d" % reply_to_status.id)

    if (dry_run):
        print("Not tweeting: %s" % message)
    else:
        print("Tweeting: %s" % message)
        return api.update_status(message, **tweet_kwargs)

if __name__ == "__main__":
    config = configparser.ConfigParser()
    config.read(CREDENTIALS_FILE)

    if os.path.isfile(PROGRESS_FILE):
        with open(PROGRESS_FILE, "r") as f:
            last_row = int(f.read())
    else:
        last_row = -1
    this_row = last_row + 1

    auth = tweepy.OAuthHandler(
        config["twitter"]["consumer_key"],
        config["twitter"]["consumer_secret"]
    )
    auth.set_access_token(
        config["twitter"]["access_token"],
        config["twitter"]["access_token_secret"]
    )
    api = tweepy.API(auth)

    #row = pandas.read_csv("tweets.csv").iloc[this_row]
    row = pandas.read_csv("tweets-with-images.csv").iloc[this_row]
    text = row["tweet"]
    image = IMAGE_TEMPLATE.format(tlid=row["TLID"])

    tweet_obj = tweet(api, text, [image])

    with open(PROGRESS_FILE, "w") as f:
        f.write(str(this_row))
