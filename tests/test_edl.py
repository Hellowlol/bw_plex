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
    assert edl.has_edl('hello.mkv') is True


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


def test_write_chapters_to_file(intro_file, tmpdir, monkeypatch, mock):
    def check_chapter(cmd):
        text = subprocess.check_output(cmd)
        chapter_info = json.loads(text)
        if chapter_info.get('chapters'):
            return True
        return False

    # Confirm that no chapters exists in that file.
    cmd = 'ffprobe -i %s -print_format json -show_chapters -loglevel error'
    assert check_chapter(cmd % str(intro_file)) is False

    f = tmpdir.join('hello.mkv')
    shutil.copyfile(intro_file, f)
    root = str(tmpdir)
    mock.patch('edl.os.path.isfile', lambda k: True)
    monkeypatch.setattr(edl, 'create_edl_path', lambda k: os.path.join(root, 'hello.edl'))

    edl_file = edl.write_edl('hello.mkv', [[1, 2, 3]])
    modified_file = edl.write_chapters_to_file(str(f), input_edl=edl_file)

    assert check_chapter(cmd % str(modified_file))
