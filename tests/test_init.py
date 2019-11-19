from conftest import bw_plex


def test_trim_args():
    a = ['bw_plex', '-d', 'watch']

    args = bw_plex.trim_argv(a)
    assert 'bw_plex' == args[0]
    assert '-d' == args[1]
    assert 'watch' not in args


def test_arg_extract(mocker):
    args = ['bw_plex', '-d', '--username', 'kek', '-p', 'mysecret', 'add_theme_to_hashtable', '-d']

    mocker.patch('bw_plex.trim_argv', return_value=args)
    kw = bw_plex.arg_extract()
    assert kw
    assert kw['username'] == 'kek'
    assert kw['password'] == 'mysecret'
    assert kw['debug'] is True
