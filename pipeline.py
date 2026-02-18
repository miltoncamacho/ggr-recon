#!/usr/bin/env python3

import os
import shlex
import subprocess
import sys

try:
	from utils import app_name, version, release_date
except Exception:
	app_name = 'GGR-recon'
	version = 'unknown'
	release_date = ''


def print_help():
	print('usage: pipeline.py [PREPROCESS_ARGS ...] [-- RECON_ARGS ...]')
	print('')
	print('Runs preprocess.py first, then recon.py.')
	print('Arguments before "--" are passed to preprocess.py.')
	print('Arguments after "--" are passed to recon.py.')
	print('')
	print('Examples:')
	print('  pipeline.py --path /data --temp_path /temp --out_path /bids')
	print('  pipeline.py --path /data --temp_path /temp --out_path /bids \\')
	print('    --bids-filter subject=2983 --bids-filter rec=filtered -- --ggr -w 0.03')
	print('')
	print('Notes:')
	print('  - If "--" is omitted, no extra args are passed to recon.py (defaults are used).')
	print('  - All original preprocess.py and recon.py arguments are supported via passthrough.')


def split_passthrough_args(argv):
	if '--' in argv:
		sep = argv.index('--')
		return argv[:sep], argv[sep + 1:]
	return argv, []


def run_script(script_name, script_args):
	script_path = os.path.join(os.path.dirname(__file__), script_name)
	cmd = [sys.executable, script_path] + script_args
	print('[pipeline] running:', ' '.join(shlex.quote(token) for token in cmd))
	result = subprocess.run(cmd)
	return result.returncode


def main():
	argv = sys.argv[1:]

	if '-h' in argv or '--help' in argv:
		print_help()
		return 0
	if '-V' in argv or '--version' in argv:
		print('%s version : v %s %s' % (app_name, version, release_date))
		return 0

	preprocess_args, recon_args = split_passthrough_args(argv)

	rc = run_script('preprocess.py', preprocess_args)
	if rc != 0:
		print('[pipeline] preprocess.py failed with exit code %d' % rc)
		return rc

	rc = run_script('recon.py', recon_args)
	if rc != 0:
		print('[pipeline] recon.py failed with exit code %d' % rc)
		return rc

	return 0


if __name__ == '__main__':
	sys.exit(main())
