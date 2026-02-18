#!/usr/bin/env python3

import os
import shlex
import subprocess
import sys

try:
	from bids import BIDSLayout
except Exception:
	BIDSLayout = None

try:
	from utils import app_name, version, release_date
except Exception:
	app_name = 'GGR-recon'
	version = 'unknown'
	release_date = ''

ACQ_ORDER = ['sag', 'cor', 'ax']
FILTER_KEY_ALIASES = {
	'sub': 'subject',
	'ses': 'session',
	'acq': 'acquisition',
	'rec': 'reconstruction',
}
GROUP_EXCLUDED_ENTITIES = {'acquisition', 'suffix', 'extension', 'datatype'}

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
	print('  - If no explicit -f/--filenames is provided, pipeline runs all complete BIDS groups matching filters.')
	print('  - All original preprocess.py and recon.py arguments are supported via passthrough.')


def split_passthrough_args(argv):
	if '--' in argv:
		sep = argv.index('--')
		return argv[:sep], argv[sep + 1:]
	return argv, []

def parse_preprocess_path(args):
	path = '/opt/GGR-recon/data/'
	ii = 0
	while ii < len(args):
		token = args[ii]
		if token in ('-p', '--path') and ii + 1 < len(args):
			path = args[ii + 1]
			ii += 2
			continue
		if token.startswith('--path='):
			path = token.split('=', 1)[1]
		ii += 1
	return path

def has_filenames_arg(args):
	return '-f' in args or '--filenames' in args

def extract_bids_filters(args):
	raw_filters = []
	ii = 0
	while ii < len(args):
		token = args[ii]
		if token == '--bids-filter' and ii + 1 < len(args):
			raw_filters.append(args[ii + 1])
			ii += 2
			continue
		if token.startswith('--bids-filter='):
			raw_filters.append(token.split('=', 1)[1])
			ii += 1
	return raw_filters

def parse_filter_key_value(raw):
	if '=' not in raw:
		return None, None
	key, value = raw.split('=', 1)
	key = FILTER_KEY_ALIASES.get(key.strip(), key.strip())
	value = value.strip()
	if key == '' or value == '':
		return None, None
	if ',' in value:
		value = [v.strip() for v in value.split(',') if v.strip() != '']
	return key, value

def group_key_from_entities(entities):
	items = []
	for key, value in entities.items():
		if value is None or key in GROUP_EXCLUDED_ENTITIES:
			continue
		items.append((key, str(value)))
	return tuple(sorted(items))

def better_path(path_a, path_b):
	if path_a is None:
		return path_b
	depth_a = path_a.count(os.sep)
	depth_b = path_b.count(os.sep)
	if depth_b < depth_a:
		return path_b
	if depth_a < depth_b:
		return path_a
	return min(path_a, path_b)

def format_group_key(group_key):
	order = {'subject': 0, 'session': 1, 'reconstruction': 2}
	pairs = sorted(group_key, key=lambda kv: (order.get(kv[0], 99), kv[0], kv[1]))
	return '_'.join('%s-%s' % (key, value) for key, value in pairs)

def discover_group_filter_sets(preprocess_args):
	if BIDSLayout is None:
		return None

	root = parse_preprocess_path(preprocess_args)
	try:
		layout = BIDSLayout(root, validate=False)
	except Exception:
		return []

	query = {
		'suffix': 'T2w',
		'acquisition': ACQ_ORDER,
		'extension': ['.nii', '.nii.gz'],
		'datatype': 'anat',
		'scope': 'raw',
	}
	for raw_filter in extract_bids_filters(preprocess_args):
		key, value = parse_filter_key_value(raw_filter)
		if key is not None:
			query[key] = value

	try:
		bids_files = layout.get(return_type='object', **query)
	except Exception:
		return []
	groups = {}
	for bids_file in bids_files:
		entities = bids_file.get_entities()
		acq = str(entities.get('acquisition', ''))
		if acq not in ACQ_ORDER:
			continue
		if entities.get('subject') is None:
			continue

		group_key = group_key_from_entities(entities)
		if group_key not in groups:
			groups[group_key] = {'acq_map': {}}
		current = groups[group_key]['acq_map'].get(acq)
		groups[group_key]['acq_map'][acq] = better_path(current, bids_file.path)

	complete = []
	for group_key, group in groups.items():
		if all(acq in group['acq_map'] for acq in ACQ_ORDER):
			filter_args = []
			for key, value in group_key:
				filter_args += ['--bids-filter', '%s=%s' % (key, value)]
			complete.append((group_key, filter_args))

	complete.sort(key=lambda item: format_group_key(item[0]))
	return complete

def run_single(preprocess_args, recon_args):
	rc = run_script('preprocess.py', preprocess_args)
	if rc != 0:
		print('[pipeline] preprocess.py failed with exit code %d' % rc)
		return rc

	rc = run_script('recon.py', recon_args)
	if rc != 0:
		print('[pipeline] recon.py failed with exit code %d' % rc)
		return rc
	return 0

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
	raw_filters = extract_bids_filters(preprocess_args)
	# Expand into all matching groups unless explicit filenames are provided.
	# This includes cases with filters (e.g., subject/session without rec).
	should_expand_groups = not has_filenames_arg(preprocess_args)

	if should_expand_groups:
		discovered = discover_group_filter_sets(preprocess_args)
		if discovered is None:
			print('[pipeline] pybids is unavailable; running a single preprocess/recon pair.')
			return run_single(preprocess_args, recon_args)
		if len(discovered) == 0:
			print('[pipeline] no complete BIDS groups found with no filters; running single pass.')
			return run_single(preprocess_args, recon_args)

		print('[pipeline] discovered %d complete BIDS groups.' % len(discovered))
		for idx, (group_key, group_filter_args) in enumerate(discovered, start=1):
			print('[pipeline] group %d/%d: %s' % (
					idx, len(discovered), format_group_key(group_key)))
			rc = run_single(preprocess_args + group_filter_args, recon_args)
			if rc != 0:
				return rc
		return 0

	return run_single(preprocess_args, recon_args)


if __name__ == '__main__':
	sys.exit(main())
