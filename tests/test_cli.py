import os
import json

from conftest import plex
import click


def test_cli():
    pass


def test_create_config(monkeypatch, cli_runner, tmpdir):
    fullpath = os.path.join(str(tmpdir), 'some_config.ini')
    res = cli_runner.invoke(plex.create_config, ['-fp', fullpath])
    click.echo(res.output)

    assert os.path.exists(fullpath)


def test_check(episode, intro_file, cli_runner, tmpdir, monkeypatch, HT, mocker):
    def fetchItem(i):
        return episode
    m = mocker.Mock()
    m.fetchItem = fetchItem

    def zomg(*args, **kwargs):
        pass

    monkeypatch.setitem(plex.CONFIG, 'theme_source', 'tvtunes')
    monkeypatch.setattr(plex, 'check_file_access', lambda k: intro_file)
    monkeypatch.setattr(plex, 'HT', HT)
    monkeypatch.setattr(plex, 'PMS', m)
    monkeypatch.setattr(plex, 'find_next', lambda k: None)
    monkeypatch.setattr(plex, 'client_jump_to', zomg)

    data = {"PlaySessionStateNotification": [{"guid": "",
                                              "key": "/library/metadata/1337",
                                              "playQueueItemID": 22631,
                                              "ratingKey": "1337",
                                              "sessionKey": "84",
                                              "state": "playing",
                                              "transcodeSession": "4avh8p7h64n4e9a16xsqvr9e",
                                              "url": "",
                                              "viewOffset": 1000}],
            "size": 1,
            "type": "playing"
            }

    # This should add the shit to the db. Lets check it.
    plex.check(data)
    plex.POOL.close()
    plex.POOL.join()

    with plex.session_scope() as se:
        assert se.query(plex.Preprocessed).filter_by(ratingKey=episode.ratingKey).one()

        # lets check that we can export db shit too.

        res = cli_runner.invoke(plex.export_db, ['-f', 'json', '-fp', str(tmpdir), '-wf'])
        print(res.output)

        fp = os.path.join(str(tmpdir), 'Preprocessed.json')
        assert os.path.exists(fp)

        with open(fp, 'r') as f:
            assert json.load(f)



def _test_process_to_db(episode, intro_file, cli_runner, tmpdir, monkeypatch, HT, mocker):
    # This is tested in check
    def fetchItem(i):
        return episode
    m = mocker.Mock()
    m.fetchItem = fetchItem

    monkeypatch.setitem(plex.CONFIG, 'theme_source', 'tvtunes')
    monkeypatch.setattr(plex, 'check_file_access', lambda k: intro_file)
    monkeypatch.setattr(plex, 'HT', HT)
    monkeypatch.setattr(plex, 'PMS', m)
    monkeypatch.setattr(plex, 'find_next', lambda k: None)

    plex.task(1337, 1)

    #plex.process_to_db(episode, vid=str(intro_file), start=10, end=20, ffmpeg_end=99, recap=False)

    with plex.session_scope() as se:
        assert se.query(plex.Preprocessed).filter_by(ratingKey=episode.ratingKey).one()

        # lets check that we can export db shit too.

        res = cli_runner.invoke(plex.export_db, ['-f', 'json', '-fp', str(tmpdir), '-wf'])
        print(res.output)

        fp = os.path.join(str(tmpdir), 'Preprocessed.json')
        assert os.path.exists(fp)

        with open(fp, 'r') as f:
            assert json.load(f)





def test_process():
    pass


def test_add_theme_to_hashtable(cli_runner, monkeypatch, HT):
    # We just want to check that this doesnt blow up..
    monkeypatch.setattr(plex, 'get_hashtable', HT)

    cli_runner.invoke(plex.add_theme_to_hashtable, [2, None])


def test_ffmpeg_process(cli_runner, intro_file):
    res = cli_runner.invoke(plex.ffmpeg_process, [intro_file])
    assert len(res.output)
    # In short we miss on this episode as we find the start of the theme, not the end.
    # correct value should be sec ~217.
    # we dont care about the result. This file is already test other places.


def test_manually_correct_theme():
    pass
