

def fake_main():
    import bw_plex
    default_folder = None
    debug = False
    config = None

    args = bw_plex.trim_argv()
    for i, e in enumerate(args):  # pragma: no cover

        if e in ('default_folder', '--default_folder', '-df'):
            default_folder = args[i + 1]

        if e in ('debug', '--debug', '-d'):
            debug = True

        if e in ('config', '--config', '-c'):
            config = args[i + 1]

    bw_plex.init(folder=default_folder, debug=debug, config=config)

    from bw_plex.plex import real_main
    real_main()


if __name__ == '__main__':
    fake_main()
