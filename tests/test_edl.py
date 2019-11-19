import json
import os
import shutil
import subprocess
from conftest import edl


def test_write_chapters_to_file(intro_file, tmpdir, monkeypatch, mock):
    def check_chapter(cmd):
        text = subprocess.check_output(cmd)
        chapter_info = json.loads(text)
        if chapter_info.get('chapters'):
            return True
        return False

    if os.name == 'nt':
        fn = '"%s"' % str(intro_file)
    else:
        fn = str(intro_file)
    # Confirm that no chapters exists in that file.
    base_cmd = ['ffprobe', '-i', fn, '-print_format', 'json', '-show_chapters', '-loglevel', 'error']

    if os.name == 'nt':
        cmd = '%s' % ' '.join(base_cmd)
    else:
        cmd = base_cmd

    assert check_chapter(cmd) is False

    f = tmpdir.join('hello.mkv')
    shutil.copyfile(intro_file, f)
    modified_file = edl.write_chapters_to_file(str(f), input_edl={"intro": [1, 2, 3]})

    new_cmd = list(base_cmd)

    if os.name == 'nt':
        fn_mod = '"%s"' % str(modified_file)
    else:
        fn_mod = str(modified_file)

    new_cmd[2] = fn_mod

    if os.name == 'nt':
        new_cmd = '%s' % ' '.join(new_cmd)

    assert check_chapter(new_cmd)
