# Librarian

![test](media/repo/screenshot.png)

## overview

a Discord bot that tracks new pull requests of the [ppy/osu-wiki](https://github.com/ppy/osu-wiki) repository. it's a GitHub web hook, except not really:

- it's not a GitHub web hook, it's a chat bot you need to host or invite
- it can be repurposed for another repository you don't own (as well as `ppy/osu-wiki`)
- it's stateful (has its own local database to work around API slowness)
- it has latency (up to 2 minutes in a worst case scenario)
- you can talk to it using miscellaneous commands. sometimes it replies

### features

- notify reviewers in Discord about new relevant pull requests
- pin a pull request in Discord and keep track of it until it's closed
- merge statistics over a time period

## usage

- [add the bot to your server](https://discord.com/api/oauth2/authorize?client_id=742750842737655830&permissions=11264&scope=bot)
- set up a channel for announcements using the `.set` command:
    ```
    .set language ru
    .set reviewer-role @role_mention  # optional, if you want to receive pings
    ```
- use `.help` for general overview
- use `.help commandname` for details on `commandname`

## host your own installation

### credentials and setup

requirements:
- `python3` and `git`
- `tmux` if you want to run it unattended

1. [create a Discord application](https://discord.com/developers/applications) and add a bot account to it.
2. add the bot to your server using a modified version of an OAuth2 authorization link from [Bot Authorization Flow](https://discord.com/developers/docs/topics/oauth2#bot-authorization-flow).
3. clone the repository:
    ```bash
    git clone https://github.com/TicClick/librarian
    ```
    create a modified version of `config/config.example.yaml` and fill in whatever data you need. to benefit from GitHub's extended API limits, query it using an API token (get one at [Personal access tokens](https://github.com/settings/tokens))
4. setup and run the bot:
    ```bash
    ./bin.sh setup
    tmux new -d -s librarian-bot "./bin.sh run --config /path/to/config"
    ```

### maintenance

stop the bot:

```bash
tmux kill-session -t librarian
```

update to the last stable version (make sure to stop the bot beforehand):

```bash
git fetch && git checkout main
git pull origin main
git checkout $( git tag --list --sort=v:refname | tail -n 1 )
```

for anything else, use `bin.sh` from the source directory:

```bash
./bin.sh setup  # install all dependencies
./bin.sh run --config /path/to/config.yaml  # start the bot
./bin.sh clean  # remove virtual environment and Python bytecode cache
./bin.sh test  # run unit tests with pytest
./bin.sh test -x -k TestDiscordCommands  # stop on the first failure of a test suite
./bin.sh coverage  # generate coverage data
./bin.sh cov  # print coverage stats in terminal
./bin.sh hcov  # render and open a nice HTML with coverage stats
./bin.sh db --config /path/to/config upgrade head  # run available schema migrations
```

if anything goes wrong, make extensive use of a runtime log located at `{runtime}/librarian.log`

## credits

- bot avatar by [@drstrange777](https://twitter.com/drstrange777)
- see `requirements.txt` for a list of cool packages
