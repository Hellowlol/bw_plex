import os

from conftest import plex
import click


def test_cli():
    pass



def test_add_theme_to_hashtable(cli_runner):
    pass
    #cli_runner(plex.add_theme_to_hashtable, ['-t 2'])




def test_create_config(monkeypatch, cli_runner, tmpdir):
    fullpath = os.path.join(str(tmpdir), 'some_config.ini')
    res = cli_runner.invoke(plex.create_config, ['-fp', fullpath])
    click.echo(res.output)

    assert os.path.exists(fullpath)



def test_process_to_db():
    pass


def test_process():
    pass


def test_ffmpeg_process(cli_runner, intro_file):
    res = cli_runner.invoke(plex.ffmpeg_process, [intro_file])
    assert len(res.output)
    # In short we miss on this episode as we find the start of the theme, not the end.
    # correct value should be sec ~217.
    # we dont care about the result. This file is already test other places.


def test_manually_correct_theme():
    pass
