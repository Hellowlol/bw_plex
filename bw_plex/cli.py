

def fake_main():
    import bw_plex
    default_folder = None
    debug = False
    config = None

    args = bw_plex.trim_argv()
    for i, e in enumerate(args):  # pragma: no cover

        if e == '--default_folder' or e == '-df':
            default_folder = args[i + 1]

        if e == '--debug' or e == '-d':
            debug = True

        if e == '--config' or e == '-c':
            config = args[i + 1]

    bw_plex.init(folder=default_folder, debug=debug, config=config)

    from bw_plex.plex import real_main
    real_main()


if __name__ == '__main__':
    fake_main()
