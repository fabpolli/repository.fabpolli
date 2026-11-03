#!/usr/bin/env python3
"""Regenerates the Kodi repository files.

Usage: python tools/build_repo.py [path/to/addon.id-1.0.0.zip ...]

Zips given on the command line are added to the repository. Published zips are
never overwritten: a change needs a new version number.
"""
import hashlib
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP = {'.git', 'src', 'tools'}
REPO_ID = 'repository.fabpolli'


def version_key(version):
    return [int(part) if part.isdigit() else 0 for part in re.split(r'[.\-~]', version)]


def read_meta(path):
    """Returns the addon.xml root and bytes of a zip, checking its layout."""
    with zipfile.ZipFile(path) as archive:
        tops = {name.split('/')[0] for name in archive.namelist()}
        if len(tops) != 1:
            sys.exit('%s: more than one top folder: %s' % (path, sorted(tops)))
        top = tops.pop()
        data = archive.read(top + '/addon.xml')
    root = ET.fromstring(data)
    addon_id, version = root.get('id'), root.get('version')
    if top != addon_id or os.path.basename(path) != '%s-%s.zip' % (addon_id, version):
        sys.exit('%s: name does not match %s %s' % (path, addon_id, version))
    return root, data


def add_zip(path):
    root, _ = read_meta(path)
    folder = os.path.join(ROOT, root.get('id'))
    target = os.path.join(folder, os.path.basename(path))
    if os.path.exists(target):
        sys.exit('already published: %s' % target)
    os.makedirs(folder, exist_ok=True)
    shutil.copyfile(path, target)
    print('added', os.path.relpath(target, ROOT))


def build_repository_zip():
    source = os.path.join(ROOT, 'src', REPO_ID)
    version = ET.parse(os.path.join(source, 'addon.xml')).getroot().get('version')
    target = os.path.join(ROOT, REPO_ID, '%s-%s.zip' % (REPO_ID, version))
    if os.path.exists(target):
        return target
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for filename in sorted(os.listdir(source)):
            archive.write(os.path.join(source, filename), '%s/%s' % (REPO_ID, filename))
    print('built', os.path.relpath(target, ROOT))
    return target


def latest_zips():
    found = []
    for name in sorted(os.listdir(ROOT)):
        folder = os.path.join(ROOT, name)
        if name in SKIP or not os.path.isdir(folder):
            continue
        zips = [z for z in os.listdir(folder) if z.endswith('.zip')]
        if zips:
            zips.sort(key=lambda z: version_key(z[len(name) + 1:-4]))
            found.append(os.path.join(folder, zips[-1]))
    return found


def extract_assets(path, root):
    """Kodi loads the art of an add-on it has not installed from the repository folder."""
    addon_id = root.get('id')
    assets = root.find(".//assets")
    with zipfile.ZipFile(path) as archive:
        for asset in (assets if assets is not None else []):
            if not asset.text:
                continue
            target = os.path.join(ROOT, addon_id, asset.text)
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target, 'wb') as handle:
                handle.write(archive.read('%s/%s' % (addon_id, asset.text)))


def write_index(repo_zip):
    """A page Kodi can browse when the address is added as a file source.

    Kodi caches this listing and then refuses to open any other file of the folder,
    so it must include the files the repository add-on reads from here.
    """
    name = os.path.basename(repo_zip)
    shutil.copyfile(repo_zip, os.path.join(ROOT, name))
    for old in os.listdir(ROOT):
        if old.startswith(REPO_ID + '-') and old.endswith('.zip') and old != name:
            os.remove(os.path.join(ROOT, old))
    links = ''.join('<a href="%s">%s</a><br>\n' % (link, link)
                    for link in (name, 'addons.xml', 'addons.xml.md5'))
    page = ('<!DOCTYPE html>\n<html>\n<head><meta charset="utf-8"><title>fabpolli Repository</title></head>\n'
            '<body>\n%s</body>\n</html>\n' % links)
    with open(os.path.join(ROOT, 'index.html'), 'w', encoding='utf-8', newline='\n') as handle:
        handle.write(page)


def main():
    for path in sys.argv[1:]:
        add_zip(path)
    repo_zip = build_repository_zip()
    blocks = []
    for path in latest_zips():
        root, data = read_meta(path)
        extract_assets(path, root)
        text = data.decode('utf-8').replace('\r\n', '\n')
        text = re.sub(r'^\s*<\?xml[^>]*\?>\s*', '', text).strip()
        blocks.append(text)
        print('listed', root.get('id'), root.get('version'))
    body = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<addons>\n%s\n</addons>\n'
            % '\n'.join(blocks)).encode('utf-8')
    ET.fromstring(body)
    with open(os.path.join(ROOT, 'addons.xml'), 'wb') as handle:
        handle.write(body)
    with open(os.path.join(ROOT, 'addons.xml.md5'), 'w', encoding='ascii', newline='\n') as handle:
        handle.write(hashlib.md5(body).hexdigest())
    write_index(repo_zip)


if __name__ == '__main__':
    main()
