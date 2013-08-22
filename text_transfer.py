from __future__ import absolute_import, unicode_literals, print_function, division

import re
import sublime_plugin
import sublime
from collections import defaultdict
import tempfile
import binascii

try:
    from .sublimerepl import manager, SETTINGS_FILE
except (ImportError, ValueError):
    from sublimerepl import manager, SETTINGS_FILE


def default_sender(repl, text, view=None):
    repl.write(text)

"""Senders is a dict of functions used to transfer text to repl as a repl
   specific load_file action"""
SENDERS = defaultdict(lambda: default_sender)


def sender(external_id,):
    def wrap(func):
        SENDERS[external_id] = func
    return wrap


@sender("python")
def python_sender(repl, text, view=None):
    text_wo_encoding = re.sub(
        pattern=r"#.*coding[:=]\s*([-\w.]+)",
        repl="# <SublimeREPL: encoding comment removed>",
        string=text,
        count=1)
    code = binascii.hexlify(text_wo_encoding.encode("utf-8"))
    execute = ''.join([
        'from binascii import unhexlify as __un; exec(compile(__un("',
        str(code.decode('ascii')),
        '").decode("utf-8"), "<string>", "exec"))\n'
    ])
    return default_sender(repl, execute, view)


@sender("ruby")
def ruby_sender(repl, text, view=None):
    code = binascii.b2a_base64(text.encode("utf-8"))
    payload = "begin require 'base64'; eval(Base64.decode64('%s'), binding=TOPLEVEL_BINDING) end\n" % (code.decode("ascii"),)
    return default_sender(repl, payload, view)


# custom clojure sender that makes sure that all selections are
# evaluated in the namespace declared by the file they are in
@sender("clojure")
def clojure_sender(repl, text, view):
    return default_sender(repl, text, view)


class ReplViewWrite(sublime_plugin.TextCommand):
    def run(self, edit, external_id, text):
        for rv in manager.find_repl(external_id):
            rv.append_input_text(text)
            break  # send to first repl found
        else:
            sublime.error_message("Cannot find REPL for '{}'".format(external_id))


class ReplSend(sublime_plugin.TextCommand):
    def run(self, edit, external_id, text, with_auto_postfix=True):
        for rv in manager.find_repl(external_id):
            if with_auto_postfix:
                text += rv.repl.cmd_postfix
            if sublime.load_settings(SETTINGS_FILE).get('show_transferred_text'):
                rv.append_input_text(text)
                rv.adjust_end()
            SENDERS[external_id](rv.repl, text, self.view)
            break
        else:
            sublime.error_message("Cannot find REPL for '{}'".format(external_id))


class ReplTransferCurrent(sublime_plugin.TextCommand):
    def run(self, edit, scope="selection", action="send"):
        text = ""
        if scope == "selection":
            text = self.selected_text()
        elif scope == "lines":
            text = self.selected_lines()
        elif scope == "function":
            text = self.selected_functions()
        elif scope == "block":
            text = self.selected_blocks()
        elif scope == "file":
            text = self.selected_file()
        cmd = "repl_" + action
        self.view.window().run_command(cmd, {"external_id": self.repl_external_id(), "text": text})

    def repl_external_id(self):
        return self.view.scope_name(0).split(" ")[0].split(".", 1)[1]

    def selected_text(self):
        v = self.view
        parts = [v.substr(region) for region in v.sel()]
        return "".join(parts)

    def selected_blocks(self):
        # TODO: Clojure only for now
        v = self.view
        strs = []
        old_sel = list(v.sel())
        v.run_command("expand_selection", {"to": "brackets"})
        v.run_command("expand_selection", {"to": "brackets"})
        for s in v.sel():
            strs.append(v.substr(s))
        v.sel().clear()
        for s in old_sel:
            v.sel().add(s)
        return "\n\n".join(strs)

    def selected_lines(self):
        v = self.view
        parts = []
        for sel in v.sel():
            for line in v.lines(sel):
                parts.append(v.substr(line))
        return "\n".join(parts)

    def selected_file(self):
        v = self.view
        return v.substr(sublime.Region(0, v.size()))
