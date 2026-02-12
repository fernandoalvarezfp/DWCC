#!/bin/python3

# mkdocs-local (for Material < v9)
#   https://github.com/wilhelmer/mkdocs-localsearch
# offline mode
#   https://squidfunk.github.io/mkdocs-material/setup/building-for-offline-usage/#configuration

import os
import random
import re
import string
import subprocess
import sys
import urllib.request

TERM_RED    = "\x1b[1;31m"
TERM_GREEN  = "\x1b[1;32m"
TERM_YELLOW = "\x1b[1;33m"
TERM_BLUE   = "\x1b[1;34m";

TERM_RESET  = "\x1b[0m"

SHOW_DIFF = False

PATH_SRC            = os.path.normpath(os.path.dirname(__file__))
PATH_SITE           = os.path.join(PATH_SRC, "site")
PATH_MKDOCS_ONLINE  = os.path.join(PATH_SRC, "mkdocs.yml")
PATH_MKDOCS_OFFLINE = os.path.join(PATH_SRC, "mkdocs-offline.yml")
PATH_3PARTY         = os.path.join(PATH_SITE, "3party")

if not os.path.isfile(PATH_MKDOCS_ONLINE):
  print(TERM_RED + "ERROR:" + TERM_RESET + " \"mkdocs.yml\" is missing. Wrong folder???", file=sys.stderr)
  exit(1)

def build_mkdocs_offline_yml():
  file = open(PATH_MKDOCS_ONLINE, "r", encoding="utf8")
  content = file.readlines()
  file.close()

  index = None
  for i in range(len(content)):
    if re.match("^plugins:.*$", content[i]):
      index = i
      break

  if index is None:
    content.append("plugins:\n")
    content.append("  - offline\n")
  else:
    content.insert(index + 1, "  - offline\n")

  file = open(PATH_MKDOCS_OFFLINE, "w", encoding="utf8")
  file.write("".join(content))
  file.close()

build_mkdocs_offline_yml()

def build_mkdocs():
  print(TERM_BLUE + "INFO:" + TERM_RESET + " Generating offline site folder\n", file=sys.stderr)
  return subprocess.run([
    "python",
      "-m",
      "mkdocs",
      "build",
      "-f",
      PATH_MKDOCS_OFFLINE
  ]).returncode

build_mkdocs_status = build_mkdocs()
os.remove(PATH_MKDOCS_OFFLINE)
if build_mkdocs_status != 0:
  exit(1)

print()

def mkdir_silent(path):
  try:
    os.mkdir(path)
  except FileExistsError as e:
    pass

mkdir_silent(PATH_3PARTY)

def get_3party_relative_path(path):
  path = path[len(PATH_SITE)+1:]
  if os.name == "nt": # windows
    path = path.replace("\\", "/")

  depth = len(path.split("/")) - 1

  return "".join("../" for _ in range(depth)) + "3party/"

def generate_random_3party_name_file():
  while True:
    file = "".join(random.choice(string.ascii_uppercase + string.digits) for _ in range(16))
    if not os.path.exists(os.path.join(PATH_3PARTY, file)):
      return file

already_downloaded = {}
def pre_fetch(url, path):
  global already_downloaded

  get_3party_relative_path(path)

  try:
    return get_3party_relative_path(path) + already_downloaded[url.group(1)]
  except KeyError as e:
    pass

  already_downloaded[url.group(1)] = generate_random_3party_name_file()

  urllib.request.urlretrieve(url.group(1), os.path.join(PATH_3PARTY, already_downloaded[url.group(1)]))

  return get_3party_relative_path(path) + already_downloaded[url.group(1)]

def inspect_dir(htmls_accumulator, dir):
  ls = os.listdir(dir)
  for i in range(len(ls)):
    f = os.path.join(dir, ls[i])
    if os.path.isdir(f):
      inspect_dir(htmls_accumulator, f)
    else:
      if re.match(".*\\.html$", f):
        htmls_accumulator.append(f)

  return htmls_accumulator

htmls = inspect_dir([], PATH_SITE)

lines_changed = 0
lines_removed = 0

for i_html in range(len(htmls)):
  file_html = open(htmls[i_html], "r", encoding="utf8")
  content_html = file_html.readlines()
  file_html.close()

  output = []
  for i_line in range(len(content_html)):
    line = content_html[i_line]
    line_copy = line
    changed = False

    if re.match("^[\\n\\r ]*$", line): # empty lines
      lines_removed += 1

    elif re.match(".* src=\"https?://", line): # external js
      line = re.sub(" src=\"(.*[^\"])\"", lambda s: " src=\"" + pre_fetch(s, htmls[i_html]) + "\"", line)
      output.append(line)
      if not changed:
        changed = True
        lines_changed += 1

    elif not " href=\"" in line: # not href
      output.append(line)

    else: # href
      if " href=\"/" in line: # "/a" => "a"
        line = re.sub(" href=\"/([^ ]+)/?\"", " href=\"\\1\"", line)
        output.append(line)
        if not changed:
          changed = True
          lines_changed += 1
        # NOT continue (it is intentional!)

      if re.match(".* href=\"https?://", line): # http[s]
        if re.match(".*<link .*rel=\"preconnect\"", line): # http[s]
          pass # its not necesary to preload with the patch

        elif re.match(".*<link .*href=", line): # external css
          line = re.sub(" href=\"(.*[^\"])\"", lambda s: " href=\"" + pre_fetch(s, htmls[i_html]) + "\"", line)
          output.append(line)
          if not changed:
            changed = True
            lines_changed += 1

        else:
          output.append(line)

      elif " href=\"#" in line: # ids
        output.append(line)

      elif re.match(".* href=\"[^ ]+\\w\"", line): # files (.css, .png, ...)
        output.append(line)

      else: # "somedir/" => "somedir/index.html"
        line = re.sub(" href=\"([^ ]*[^/])/?\"", " href=\"\\1/index.html\"", line)
        output.append(line)
        if not changed:
          changed = True
          lines_changed += 1

    if SHOW_DIFF and changed:
      print(TERM_BLUE + "@" + TERM_RESET + " " + htmls[i_html] + ":" + str(i_line), file=sys.stderr)
      print(TERM_RED + "- " + line_copy + TERM_RESET, file=sys.stderr, end="")
      print(TERM_GREEN + "+ " + line + TERM_RESET, file=sys.stderr, end="")

  file_html = open(htmls[i_html], "w", encoding="utf8")
  file_html.write("".join(output))
  file_html.close()

if SHOW_DIFF:
  print()

print(TERM_YELLOW + str(lines_changed) + TERM_RESET + " lines changed", file=sys.stderr)
print(TERM_YELLOW + str(lines_removed) + TERM_RESET + " empty lines removed", file=sys.stderr)

print()

print("=> " + TERM_GREEN + os.path.join(PATH_SITE, "index.html") + TERM_RESET + " <=", file=sys.stderr)
