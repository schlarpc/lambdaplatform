import urllib.request


def handler(event):
    return urllib.request.urlopen("https://checkip.amazonaws.com").read().decode("utf-8").strip()
