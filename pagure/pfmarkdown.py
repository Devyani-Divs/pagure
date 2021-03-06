# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301,
# USA.

""" Pagure-flavored Markdown

Author: Ralph Bean <rbean@redhat.com>
"""

import flask

import markdown.inlinepatterns
import markdown.util

import pagure
import pagure.lib


def inject():
    """ Hack out python-markdown to do the autolinking that we want. """

    # First, make it so that bare links get automatically linkified.
    markdown.inlinepatterns.AUTOLINK_RE = '(%s)' % '|'.join([
        r'<(?:f|ht)tps?://[^>]*>',
        r'\b(?:f|ht)tps?://[^)<>\s]+[^.,)<>\s]',
        r'\bwww\.[^)<>\s]+[^.,)<>\s]',
        r'[^(<\s]+\.(?:com|net|org)\b',
    ])

    # Second, build some Pattern objects for @mentions, #bugs, etc...
    class MentionPattern(markdown.inlinepatterns.Pattern):
        def handleMatch(self, m):
            name = markdown.util.AtomicString(m.group(2))
            text = ' @%s' % name
            user = pagure.lib.search_user(pagure.SESSION, username=name)
            if not user:
                return text

            el = markdown.util.etree.Element("a")
            url = flask.url_for('view_user', username=name)
            el.set('href', url)
            el.text = text
            return el

    class ExplicitForkIssuePattern(markdown.inlinepatterns.Pattern):
        def handleMatch(self, m):
            user = markdown.util.AtomicString(m.group(2))
            repo = markdown.util.AtomicString(m.group(3))
            idx = markdown.util.AtomicString(m.group(4))
            text = '%s/%s#%s' % (user, repo, idx)

            if not _issue_exists(user, repo, idx):
                return text

            return _issue_anchor_tag(user, repo, idx, text)

    class ExplicitMainIssuePattern(markdown.inlinepatterns.Pattern):
        def handleMatch(self, m):
            repo = markdown.util.AtomicString(m.group(2))
            idx = markdown.util.AtomicString(m.group(3))
            text = ' %s#%s' % (repo, idx)

            if not _issue_exists(None, repo, idx):
                return text

            return _issue_anchor_tag(None, repo, idx, text)

    class ImplicitIssuePattern(markdown.inlinepatterns.Pattern):
        def handleMatch(self, m):
            idx = markdown.util.AtomicString(m.group(2))
            text = ' #%s' % idx

            root = flask.request.url_root
            url = flask.request.url
            user = None
            if 'fork/' in flask.request.url:
                user, repo = url.split('fork/')[1].split('/', 2)[:2]
            else:
                repo = url.split(root)[1].split('/', 1)[0]

            if not _issue_exists(user, repo, idx):
                return text

            return _issue_anchor_tag(user, repo, idx, text)

    MENTION_RE = r'[^|\w]@(\w+)'
    EXPLICIT_FORK_ISSUE_RE = r'(\w+)/(\w+)#([0-9]+)'
    EXPLICIT_MAIN_ISSUE_RE = r'[^|\w](?<!\/)(\w+)#([0-9]+)'
    IMPLICIT_ISSUE_RE = r'[^|\w](?<!\w)#([0-9]+)'

    # Lastly, monkey-patch the build_inlinepatterns func to insert our patterns
    original_builder = markdown.build_inlinepatterns

    def extended_builder(m, **kwargs):
        patterns = original_builder(m, **kwargs)
        patterns['mention'] = MentionPattern(MENTION_RE, m)
        patterns['explicit_fork_issue'] = ExplicitForkIssuePattern(
            EXPLICIT_FORK_ISSUE_RE, m)
        patterns['explicit_main_issue'] = ExplicitMainIssuePattern(
            EXPLICIT_MAIN_ISSUE_RE, m)
        patterns['implicit_issue'] = ImplicitIssuePattern(IMPLICIT_ISSUE_RE, m)
        return patterns

    markdown.build_inlinepatterns = extended_builder


def _issue_exists(user, repo, idx):
    repo_obj = pagure.lib.get_project(
        pagure.SESSION, name=repo, user=user)
    if not repo_obj:
        return False

    issue_obj = pagure.lib.search_issues(
        pagure.SESSION, repo=repo_obj, issueid=idx)
    if not issue_obj:
        return False

    return True


def _issue_anchor_tag(user, repo, idx, text):
    el = markdown.util.etree.Element("a")
    url = flask.url_for('view_issue', username=user, repo=repo, issueid=idx)
    el.set('href', url)
    el.text = text
    return el
