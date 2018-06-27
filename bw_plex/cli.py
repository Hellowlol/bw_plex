import os
import sys


def fake_main():
    default_folder = None
    debug = False
    config = None
    subcommands = ['watch', 'add_theme_to_hashtable', 'check_db', 'export_db',
                   'ffmpeg_process', 'manually_correct_theme', 'process', 'match',
                   'set_manual_theme_time', 'test_a_movie']

    def trim_argv():
        args = sys.argv[:]
        for cmd in subcommands:
            try:
                idx = args.index(cmd)
                return args[idx:]
            except ValueError:
                pass

        return []

    for i, e in enumerate(trim_argv()):

        if e == '--default_folder' or e == '-df':
            default_folder = sys.argv[i + 1]

        if e == '--debug' or e == '-d':
            debug = True

        if e == '--config' or e == '-c':
            config = sys.argv[i + 1]

    import bw_plex
    bw_plex.init(folder=default_folder, debug=debug, config=config)


    from bw_plex.plex import real_main
    real_main()


if __name__ == '__main__':
    fake_main()
