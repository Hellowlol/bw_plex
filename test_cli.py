import click



@click.group()
@click.option('-d', '--debug')
def lol(debug):
    click.echo(debug)



if __name__ == '__main__':
    lol()
