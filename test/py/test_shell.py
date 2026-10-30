#!/usr/bin/env python3
"""moirai.agent.shell, pure Python (no native module): the files a shell line
names (``shell_files``, which the recorder uses) and how a command is shown
(``command_lines``, ``command_language``, ``command_summary``)."""
import os
import sys
import tempfile
import unittest


class CommandFormatTests(unittest.TestCase):
    """A program handed to an interpreter is shown as a program."""

    def setUp(self):
        from moirai.agent import shell

        self.fmt = shell

    def test_ansi_c_quoting_becomes_the_program_it_encodes(self):
        # The exact shape an agent sends: a whole script as one argument, with
        # every newline escaped. As one line it is unreadable.
        command = "python3 -c $'import csv\\nrows=[]\\nprint(len(rows))'"
        block = self.fmt.command_lines(command)
        self.assertIn("\nimport csv\nrows=[]\nprint(len(rows))", block)
        self.assertNotIn("\\n", block)
        self.assertEqual(self.fmt.command_language(command), "python")

    def test_the_invocation_is_kept_as_a_comment(self):
        # A comment in the program's own language, so the whole block is one
        # piece of valid source and highlights in a single pass.
        block = self.fmt.command_lines("python3 -c $'x=1\\ny=2\\nprint(x+y)'")
        self.assertTrue(block.startswith("# python3 -c"), block)
        self.assertIn("3 lines of python", block)

    def test_a_heredoc_program_is_pulled_out_of_its_marker(self):
        command = "python3 - <<'PY'\nimport csv\nprint(csv)\nPY"
        block = self.fmt.command_lines(command)
        self.assertIn("# python3 - <<'PY'", block)
        self.assertIn("import csv\nprint(csv)", block)
        self.assertNotIn("\nPY", block)
        self.assertEqual(self.fmt.command_language(command), "python")

    def test_a_shell_chain_is_split_at_its_operators(self):
        command = (
            "ls data && head -n 5 data/house_prices.csv && "
            "wc -l data/house_prices.csv && echo done"
        )
        block = self.fmt.command_lines(command)
        self.assertEqual(block.splitlines()[0], "ls data")
        self.assertIn("  && wc -l data/house_prices.csv", block)
        self.assertEqual(self.fmt.command_language(command), "bash")

    def test_an_operator_inside_a_program_is_not_a_chain(self):
        # Splitting a quoted `;` would cut a program in half.
        command = "awk 'BEGIN { x = 1; y = 2; print x && y }' " + "f" * 60
        self.assertEqual(self.fmt.command_lines(command), command)

    def test_a_short_command_is_left_exactly_as_written(self):
        for command in ("head -n 20 data/house_prices.csv", "ls && pwd", "bash -c 'ls'"):
            self.assertEqual(self.fmt.command_lines(command), command)

    def test_a_pattern_flag_is_not_mistaken_for_a_program(self):
        # `grep -e` takes a pattern, not a program; only interpreters known to
        # take one are treated that way.
        command = "grep -e " + "'" + "x" * 90 + "'" + " data/house_prices.csv"
        self.assertEqual(self.fmt.command_lines(command), command)
        self.assertEqual(self.fmt.command_language(command), "bash")

    def test_the_interpreter_does_not_have_to_be_the_first_word(self):
        # Agents write the prefixed forms as often as the bare one, and the
        # quoted argument is a python program in every one of them.
        body = "import csv\\nrows=[]\\nwith open(\'d.csv\') as f:\\n    print(f)"
        for command in (
            f"cd data && python3 -c $'{body}'",
            f"PYTHONPATH=. python3 -c $'{body}'",
            f"env PYTHONHASHSEED=0 python3 -c $'{body}'",
            f"cat f.csv | python3 -c $'{body}'",
        ):
            self.assertEqual(self.fmt.command_language(command), "python", command)
            block = self.fmt.command_lines(command)
            self.assertIn("\nimport csv\nrows=[]", block)
            self.assertIn("lines of python", block)

    def test_the_prefix_is_kept_so_the_call_is_still_identifiable(self):
        block = self.fmt.command_lines(
            "cd data && python3 -c $'import csv\\nrows=[]\\nprint(len(rows))'"
        )
        self.assertTrue(block.startswith("# cd data && python3 -c"), block)

    def test_a_shell_wrapping_an_interpreter_is_followed_through(self):
        # `bash -c "python3 -c '...'"` is a python program behind one door.
        command = "bash -c \"python3 -c $'import csv\\nrows=[]\\nprint(len(rows))'\""
        self.assertEqual(self.fmt.command_language(command), "python")
        block = self.fmt.command_lines(command)
        self.assertIn("bash -c … python3 -c", block)
        self.assertIn("\nimport csv\nrows=[]\nprint(len(rows))", block)

    def test_a_heredoc_after_a_chain_is_still_that_interpreters_program(self):
        command = "cd data && python3 - <<'PY'\nimport csv\nprint(csv)\nPY"
        self.assertEqual(self.fmt.command_language(command), "python")
        self.assertIn("lines of python", self.fmt.command_lines(command))

    def test_a_long_program_says_how_much_it_left_out(self):
        body = "\\n".join(f"print({n})" for n in range(self.fmt.MAX_PROGRAM_LINES + 25))
        block = self.fmt.command_lines(f"python3 -c $'{body}'")
        self.assertIn("... 25 more line(s)", block)

    def test_a_title_names_the_program_rather_than_its_quoting(self):
        title = self.fmt.command_summary(
            "python3 -c $'import csv\\nrows=[]\\nwith open(\"d.csv\") as f:\\n    pass'"
        )
        self.assertTrue(title.startswith("python3 -c (4 lines)"), title)
        # Not the imports: every analysis script starts the same way, and a
        # title that says `import csv` tells a reader nothing.
        self.assertIn("with open", title)
        self.assertNotIn("$'", title)

    def test_a_title_is_cut_to_length(self):
        title = self.fmt.command_summary("echo " + "x" * 200, limit=40)
        self.assertEqual(len(title), 43)
        self.assertTrue(title.endswith("..."))

    def test_the_language_reaches_the_dashboard_with_the_block(self):
        # The dashboard highlights with it, so it travels alongside the text.
        from moirai.agent.shell import command_language, command_lines

        for command, language in (
            ("node -e 'let a=1;\nconsole.log(a)'", "javascript"),
            ("perl -e 'my $x = 1;\nprint $x;'", "perl"),
            ("bash -c 'for f in *; do\n  echo $f\ndone'", "bash"),
            ("head -3 f.csv", "bash"),
        ):
            self.assertEqual(command_language(command), language, command)
            self.assertTrue(command_lines(command))


class ShellFilesTests(unittest.TestCase):
    def setUp(self):
        from moirai.agent import shell

        self.shell = shell
        self.temp = tempfile.TemporaryDirectory()
        self.cwd = os.path.realpath(self.temp.name)
        for name in ("data.csv", "gen.py", "run.sh"):
            with open(os.path.join(self.cwd, name), "w") as fh:
                fh.write("x\n")
        os.chmod(os.path.join(self.cwd, "run.sh"), 0o755)
        os.mkdir(os.path.join(self.cwd, "out"))

    def tearDown(self):
        self.temp.cleanup()

    def files(self, command):
        s, r, w = self.shell.shell_files(command, self.cwd)
        rel = lambda paths: [os.path.relpath(p, self.cwd) for p in paths]
        return rel(s), rel(r), rel(w)

    def test_an_interpreters_argument_is_a_script_and_data_is_read(self):
        self.assertEqual(self.files("python3 gen.py data.csv"),
                         (["gen.py"], ["data.csv"], []))

    def test_an_executable_run_by_path_is_a_script(self):
        self.assertEqual(self.files("./run.sh data.csv"),
                         (["run.sh"], ["data.csv"], []))

    def test_a_redirect_target_is_written_even_if_it_is_not_there(self):
        self.assertEqual(self.files("cat data.csv > out/new.txt"),
                         ([], ["data.csv"], ["out/new.txt"]))

    def test_a_named_output_in_an_existing_directory_may_be_written(self):
        self.assertEqual(self.files("sort data.csv out/sorted.csv"),
                         ([], ["data.csv"], ["out/sorted.csv"]))

    def test_a_chain_starts_a_command_after_each_operator(self):
        self.assertEqual(self.files("ls out && python3 gen.py; ./run.sh"),
                         (["gen.py", "run.sh"], [], []))

    def test_an_unbalanced_line_names_nothing(self):
        self.assertEqual(self.files("echo 'unterminated"), ([], [], []))


if __name__ == "__main__":
    unittest.main()
