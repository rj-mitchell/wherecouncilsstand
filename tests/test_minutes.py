"""Minutes HTML to text."""

from councils.parse.minutes import to_text


def test_word_html_to_lines():
    html = ('&lt;div class="WordSection1"&gt;&lt;p class="MsoNormal"&gt;&lt;span&gt;The amendment was put to the vote '
            'and was lost.&lt;/span&gt;&lt;/p&gt;&lt;p class="MsoNormal"&gt;&amp;nbsp;&lt;/p&gt;&lt;p&gt;In favour:- '
            'Councillors A, B&lt;br&gt;Against:- Councillor C&lt;/p&gt;&lt;/div&gt;')
    assert to_text(html) == ("The amendment was put to the vote and was lost.\nIn favour:- Councillors A, B\n"
                             "Against:- Councillor C")


def test_table_cells_joined():
    assert to_text("<table><tr><td>For</td><td>12</td></tr><tr><td>Against</td><td>3</td></tr></table>") == \
        "For | 12\nAgainst | 3"


def test_empty():
    assert to_text("") == "" and to_text(None) == ""
