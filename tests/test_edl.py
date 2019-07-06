import json
import os
import shutil
import subprocess
from conftest import edl


def test_write_edl(tmpdir, monkeypatch, mock):
    root = str(tmpdir)
    mock.patch('edl.os.path.isfile', lambda k: True)
    monkeypatch.setattr(edl, 'create_edl_path', lambda k: os.path.join(root, 'hello.edl'))

    edl_file = edl.write_edl('hello.mkv', [[1,2,3]])

    with open(edl_file, 'r') as f:
        result = f.read()
        assert result == '1    2    3\n'


def test_has_edl(tmpdir, mock):
    mock.patch('edl.os.path.isfile', side_effect=[True, True])
    assert edl.has_edl('hello.mkv')


def test_dir_has_edl(tmpdir):
    root = str(tmpdir)
    edl_file_string = 'some_file.edl'
    fil = tmpdir.join(edl_file_string)
    edl_string = '1    3    3'
    fil.write(edl_string)

    assert len(edl.dir_has_edl(root))


def test_edl_path(tmpdir):
    f = 'zomg.mkv'
    edl_file = edl.create_edl_path(f)
    assert edl_file == 'zomg.edl'


#def test_ffprobe():
#    assert subprocess.check_call(['ffprobe', '-h']) == 0


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
    root = str(tmpdir)
    mock.patch('edl.os.path.isfile', lambda k: True)
    monkeypatch.setattr(edl, 'create_edl_path', lambda k: os.path.join(root, 'hello.edl'))

    edl_file = edl.write_edl('hello.mkv', [[1, 2, 3]])
    modified_file = edl.write_chapters_to_file(str(f), input_edl=edl_file)

    new_cmd = list(base_cmd)

    if os.name == 'nt':
        fn_mod = '"%s"' % str(modified_file)
    else:
        fn_mod = str(modified_file)

    new_cmd[2] = fn_mod

    if os.name == 'nt':
        new_cmd = '%s' % ' '.join(new_cmd)

    assert check_chapter(new_cmd)
