import os
import json

from conftest import plex
import click


def test_cli(cli_runner):
    res = cli_runner.invoke(plex.cli, ['--help'])
    click.echo(res.output)


def test_create_config(monkeypatch, cli_runner, tmpdir):
    fullpath = os.path.join(str(tmpdir), 'some_config.ini')
    res = cli_runner.invoke(plex.create_config, ['-fp', fullpath])
    click.echo(res.output)

    assert os.path.exists(fullpath)


def test_check(episode, film, intro_file, cli_runner, tmpdir, monkeypatch, HT, mocker):
    def fetchItem_ep(i):
        return episode

    def fetchItem_film(i):
        return film

    mf = mocker.Mock()
    mf.fetchItem = fetchItem_film

    m = mocker.Mock()
    m.fetchItem = fetchItem_ep

    def zomg(*args, **kwargs):
        pass

    monkeypatch.setitem(plex.CONFIG['tv'], 'theme_source', 'tvtunes')
    monkeypatch.setattr(plex, 'HT', HT)
    monkeypatch.setattr(plex, 'PMS', m)
    monkeypatch.setitem(plex.CONFIG['tv'], 'check_credits', True)
    monkeypatch.setitem(plex.CONFIG['tv'], 'process_deleted', True)
    # monkeypatch.setitem(plex.CONFIG['movie'], 'process_deleted', True)
    monkeypatch.setattr(plex, 'check_file_access', lambda k: intro_file)

    monkeypatch.setattr(plex, 'find_next', lambda k: None)
    monkeypatch.setattr(plex, 'client_action', zomg)

    # tv
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
    r = plex.check(data)
    # if we get a async result we want to block it
    # this is done so this test can run independently
    if r is not None:
        r.get()
    #plex.POOL.close()
    #plex.POOL.join()

    # Lets try again is the added same shit
    # as the the same info will come each tick.
    rr = plex.check(data)
    if rr is not None:
      rr.get()

    with plex.session_scope() as se:
        assert se.query(plex.Processed).filter_by(ratingKey=episode.ratingKey).one()

        # lets check that we can export db shit too.
        tmp = str(tmpdir)
        res = cli_runner.invoke(plex.export_db, ['-f', 'json', '-fp', tmp, '-wf'])
        assert res.exit_code == 0
        # print(res.output)

        fp = os.path.join(tmp, 'Processed.json')
        assert os.path.exists(fp)

        with open(fp, 'r') as f:
            assert json.load(f)


    item_deleted = {"type": "timeline",
            "size": 1,
            "TimelineEntry": [{"identifier": "com.plexapp.plugins.library",
                               "sectionID": 2,
                               "itemID": 1337,
                               "type": 4,
                               "title": "Dexter S01 E01",
                               "state": 9,
                               "mediaState": "deleted",
                               "queueSize": 8,
                               "updatedAt": 1526744644}]
            }

    r = plex.check(item_deleted)
    if r:
        r.get()

    monkeypatch.setattr(plex, 'PMS', mf)
    data_movie = {"PlaySessionStateNotification": [{"guid": "",
                                                    "key": "/library/metadata/7331",
                                                    "playQueueItemID": 22631,
                                                    "ratingKey": "7331",
                                                    "sessionKey": "84",
                                                    "state": "playing",
                                                    "transcodeSession": "4avh8p7h64n4e9a16xsqvr9e",
                                                    "url": "",
                                                    "viewOffset": 1000}],
                  "size": 1,
                  "type": "playing"
                  }

    r = plex.check(data_movie)
    if r:
        r.get()


def _test_process_to_db(episode, intro_file, cli_runner, tmpdir, monkeypatch, HT, mocker):
    # This is tested in check
    def fetchItem(i):
        return episode
    m = mocker.Mock()
    m.fetchItem = fetchItem

    monkeypatch.setitem(plex.CONFIG['tv'], 'theme_source', 'tvtunes')
    monkeypatch.setattr(plex, 'check_file_access', lambda k: intro_file)
    monkeypatch.setattr(plex, 'HT', HT)
    monkeypatch.setattr(plex, 'PMS', m)
    monkeypatch.setattr(plex, 'find_next', lambda k: None)

    plex.task(1337, 1)

    with plex.session_scope() as se:
        assert se.query(plex.Preprocessed).filter_by(ratingKey=episode.ratingKey).one()

        # lets check that we can export db shit too.
        res = cli_runner.invoke(plex.export_db, ['-f', 'json', '-fp', str(tmpdir), '-wf'])
        # print(res.output)

        fp = os.path.join(str(tmpdir), 'Preprocessed.json')
        assert os.path.exists(fp)

        with open(fp, 'r') as f:
            assert json.load(f)


def test_process(cli_runner, monkeypatch, episode, film, media, HT, intro_file, mocker):
    # Let the mock begin..
    mocker.patch.object(plex, 'find_all_movies_shows', side_effect=[[media], [episode]])
    mocker.patch('click.prompt', side_effect=['0', '0'])

    def fetchItem_ep(i):
        return episode

    def fetchItem_m(i):
        return film

    m = mocker.Mock()
    m.fetchItem = fetchItem_ep

    def zomg(*args, **kwargs):
        pass

    mf = mocker.Mock()
    mf.fetchItem = fetchItem_m

    monkeypatch.setattr(plex, 'PMS', m)
    monkeypatch.setitem(plex.CONFIG['tv'], 'theme_source', 'tvtunes')
    monkeypatch.setattr(plex, 'check_file_access', lambda k: intro_file)
    monkeypatch.setattr(plex, 'HT', HT)

    monkeypatch.setattr(plex, 'find_next', lambda k: None)

    res = cli_runner.invoke(plex.process, ['-n', 'dexter', '-s', '1', '-t', '2'])
    print(res.output)

    monkeypatch.setattr(plex, 'PMS', mf)
    res = cli_runner.invoke(plex.process, ['-n', 'Random', '-s', '1', '-sd'])
    print(res.output)


def test_add_theme_to_hashtable(cli_runner, monkeypatch, HT):
    # We just want to check that this doesnt blow up..
    monkeypatch.setattr(plex, 'get_hashtable', HT)
    ret = cli_runner.invoke(plex.add_theme_to_hashtable, [2, None])
    assert ret.exit_code == 0



def test_ffmpeg_process(cli_runner, intro_file):
    res = cli_runner.invoke(plex.ffmpeg_process, [intro_file])
    assert len(res.output)
    assert res.exit_code == 0
    # In short we miss on this episode as we find the start of the theme, not the end.
    # correct value should be sec ~217.
    # we dont care about the result. This file is already test other places.


def _test_manually_correct_theme():
    pass
