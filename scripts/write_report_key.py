"""Writes the bug-report key into a build: <module folder>/incad/_report_key.py (⚙ ▸ Report a Bug sends with it).
The key is read from a file on the builder's Mac, never from git (GitHub revokes a key it finds in a public repository):
~/.config/inncad/github-issues-token, or the file INCAD_REPORT_KEY_FILE names. No file: a note, and the build reports
through the browser instead. Usage: python3 scripts/write_report_key.py <the build's InCad module folder>"""
import os
import sys

KEY_FILE = os.environ.get("INCAD_REPORT_KEY_FILE") or os.path.expanduser("~/.config/inncad/github-issues-token")


def main(module_dir):
    sys.path.insert(0, module_dir)  # the masking of the very module the key goes into
    from incad.core import bugreport
    target = os.path.join(module_dir, "incad", "_report_key.py")
    if not os.path.isfile(KEY_FILE):
        print("NOTE: no bug-report key (%s): Report a Bug opens GitHub in the browser in this build" % KEY_FILE)
        return 0
    with open(KEY_FILE) as f:
        plain = f.read().strip()
    if not plain:
        print("NOTE: the bug-report key file is empty: Report a Bug opens GitHub in the browser in this build")
        return 0
    with open(target, "w") as f:
        f.write('"""Written by scripts/write_report_key.py for this build; never committed."""\nKEY = "%s"\n'
                % bugreport.masked(plain))
    print("bug-report key written into the build")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
