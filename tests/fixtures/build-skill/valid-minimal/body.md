<!--
This comment block shows marker syntax examples that the parser must
ignore. The next line is marker-shaped at column 0, but it is still
inside this comment block, so it is not a real marker (note that its
own closing sequence also terminates this comment block):
<!-- split:helper_start example-inside-comment.md -->

An indented marker-shaped line is never a marker (leading whitespace):
  <!-- split:helper_end -->

# Test Skill

Some content here.

<!-- split:helper_start helper-a.md -->

Content of helper A.

<!-- split:helper_end -->

Some text between markers.

<!-- split:helper_start helper-b.md -->
Line one of B.
Line two of B.
<!-- split:helper_end -->

End of document.
