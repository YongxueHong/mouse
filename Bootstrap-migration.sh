#!/usr/bin/env bash
unalias -a
trap "_exit" 1 2 3 15

_usage()
{
    echo "Usage: sh Bootstrap-migration.sh [destination ip]"
}

# set an initial value for the flag
QUIET=false
VERBOSE=true

_log()          { if ! $QUIET; then echo -e $*; fi; }
_log_info()     { _log "\033[32mINFO\033[0m\t" $*; }
_log_warn()     { _log "\033[33mWARN\033[0m\t" $*; }
_log_error()    { _log "\033[31mERROR\033[0m\t" $*; }

_within_dir()   { pushd . >/dev/null; cd $1; }
_go_back()      { popd >/dev/null; }

_exit()
{
    local RET=${1:-0}
    if [ $RET -ne 0 ]; then
        _log "Please handle the ERROR(s) and re-run this script"
    fi
    exit $RET
}
_exit_on_error() { if [ $? -ne 0 ]; then _log_error $*; _exit 1; fi; }
_warn_on_error() { if [ $? -ne 0 ]; then _log_warn $*; fi; }

_exec_cmd()
{
    local CMD=$*
    if $QUIET || (! $VERBOSE); then
        eval "$CMD" &>/dev/null
    else
        _log "\033[1m=> $CMD\033[0m"
        eval "$CMD"
    fi
    return $?
}


if [ ! -n "$1" ]
then
    _log_error "Please specify a destination ip."
    _usage
    exit 1
else
    _log "update the clock of $1"
    _exec_cmd "ssh root@$1 ntpdate clock.redhat.com"
    _exit_on_error "Failed to update the clock of $1"
    _log "update the clock of local host"
    _exec_cmd "ntpdate clock.redhat.com"
    _exit_on_error "Failed to update the clock of local host"
fi
