# Adds JS import statement autocompletion using AST information from Flow

import sublime_plugin
import sublime
import re
import time
import pprint
import os
import json
from pathlib import Path

pp = pprint.PrettyPrinter(indent=4)

def log(*args):
    # print(*args)
    pass

def dump(name, val):
    # print (name + ": ")
    # pp.pprint(val)
    pass

def plugin_loaded():
    global settings
    settings = sublime.load_settings('FlowImports.sublime-settings')

"""
import type
"""  

class FlowImports(sublime_plugin.EventListener):
    reindex_interval = 1
    found_exports_time = 0
    found_exports = {}

    def on_query_completions(self, view, prefix, locations):
        log("on_query_completions")
        if not view.match_selector(locations[0], "source.js"):
            log (view.scope_name(locations[0]) + " doesnt match")
            return None
        # dump('view',view)
        dump('prefix',prefix)
        dump('locations',locations)
        dump('line', view.line(locations[0]))
        line = view.line(locations[0])
        dump('view.scope_name(locations[0])', view.scope_name(locations[0]))
        line_str = view.substr(line)

        dump('file_name()', view.file_name())

        dump('line text', line_str)
        if not 'import ' in view.substr(line):
            return None

        basedir = Path(view.file_name()).parent

        self.maybe_get_exports(basedir)

        named_import = '{' in view.substr(line)

        js_extension_pattern = r'\.js$'
 
        matches = []
        required_path_prefix = str(basedir)
        for filepath_key, file_found_exports in FlowImports.found_exports.items():
            if filepath_key.startswith(required_path_prefix):
                for found_export in file_found_exports:
                    identifier = found_export['identifier']
                    dump('found_export',found_export)
                    filepath = found_export['filepath']
                    filepath_rel = "./{}".format(re.sub(js_extension_pattern, '', str(Path(filepath).relative_to(basedir))))
                    trigger = "{}\t{}".format(identifier,filepath_rel)
                    if named_import:
                        if found_export['type'] == 'ExportNamedDeclaration':
                            if '} from ' in line_str:
                                # just add import name, not from 'filepath' part
                                matches.append((trigger, identifier))
                            else:
                                matches.append((trigger, "{}}} from '{}';".format(identifier, filepath_rel)))
                    else:
                        if found_export['type'] ==  'ExportDefaultDeclaration':
                            matches.append((trigger, "{} from '{}';".format(identifier, filepath_rel)))

        return matches

    def on_post_text_command(self, view, command_name, args):
        if command_name == 'commit_completion':
            line = view.line(view.sel()[0])
            if re.search(r'import.*\{.*\}.*from.*;.*\}', view.substr(line)):
                # clean up extraneous semicolon
                view.run_command("flow_import_cleanup", {"line_point": line.a})
                view.run_command("move_to", {"to": 'eol'})

    files_mtimes = {}
    def maybe_get_exports(self, basedir):
        ts = time.time()
        if ts - FlowImports.found_exports_time > FlowImports.reindex_interval:
            FlowImports.found_exports_time = ts
            for filename in basedir.glob('**/*.js'):
                filepath_abs = filename.resolve()
                filepath_abs_str = str(filepath_abs)
                if not should_find_imports_in_file_lite(filepath_abs_str):
                    log('should_find_imports_in_file_lite=False',filepath_abs_str)
                    continue

                stats = filepath_abs.stat()
                has_mtime = filepath_abs_str in FlowImports.files_mtimes
                fresh = False

                if has_mtime and FlowImports.files_mtimes[filepath_abs_str] >= stats.st_mtime:
                    fresh = True

                if not fresh:
                    # clear cache of found exports for file
                    if filepath_abs_str in FlowImports.found_exports:
                        del FlowImports.found_exports[filepath_abs_str]
                    log('getting imports from ',filepath_abs_str)
                    dump('filepath_abs_str', filepath_abs_str)
                    if should_find_imports_in_file(filepath_abs_str):
                        get_imports(filepath_abs_str, FlowImports.found_exports)
                else:
                    log('no need to recheck file',stats.st_mtime,filepath_abs_str)
                FlowImports.files_mtimes[filepath_abs_str] = stats.st_mtime

class FlowImportCleanupCommand(sublime_plugin.TextCommand):
    # slice off the last char from the line, because it's an extraneous semicolon
    def run(self, edit, line_point):
        line = self.view.line(line_point)
        self.view.replace(edit, line, self.view.substr(line)[:-1])

def should_find_imports_in_file(filepath):
    if not should_find_imports_in_file_lite(filepath):
        return False

    with open(filepath,'r') as contents:
        if '@flow' in contents.read():
            return True

    return False

def should_find_imports_in_file_lite(filepath):
    if not filepath.endswith(".js"):
        log('should_find_imports_in_file_lite endswith.js excluding', filepath)
        return False

    for exclude in settings.get("ignored_dirs", []):
        if exclude in filepath:
            log('should_find_imports_in_file_lite ignored_dirs excluding', filepath, exclude)
            return False

    return True

def get_flow_path():
    return settings.get("flow_bin", "flow")

def get_imports(filepath, found_exports):
    start = time.time()
    json_string = os.popen("%s ast '%s'" %(get_flow_path(), filepath)).read()
    log('get_imports',filepath,'took',time.time() - start,'seconds')

    dump('get_imports',filepath)
    # dump('ast',json_string)


    for node in json.loads(json_string)['body']:
        if node['type'] in ['ExportNamedDeclaration', 'ExportDefaultDeclaration']:
            declaration = node['declaration']
            
            if 'id' in declaration:
                log('found', declaration['id']['name'])
                found_exports.setdefault(filepath, []).append({
                    "type": node['type'],
                    "filepath": filepath,
                    "identifier": declaration['id']['name']
                })
            elif 'declarations' in declaration:
                for var_declaration in declaration['declarations']:
                    log('found named', var_declaration['id']['name'])
                    found_exports.setdefault(filepath, []).append({
                        "type": node['type'],
                        "filepath": filepath,
                        "identifier": var_declaration['id']['name']
                    })

    return found_exports
