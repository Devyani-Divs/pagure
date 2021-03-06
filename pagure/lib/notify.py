# -*- coding: utf-8 -*-

"""
 (c) 2014-2015 - Copyright Red Hat Inc

 Authors:
   Pierre-Yves Chibon <pingou@pingoured.fr>

pagure notifications.
"""

import datetime
import urlparse
import smtplib
import time
import warnings

import flask
import pagure

from email.mime.text import MIMEText


def fedmsg_publish(*args, **kwargs):  # pragma: no cover
    ''' Try to publish a message on the fedmsg bus. '''
    ## We catch Exception if we want :-p
    # pylint: disable=W0703
    ## Ignore message about fedmsg import
    # pylint: disable=F0401
    kwargs['modname'] = 'pagure'
    try:
        import fedmsg
        fedmsg.publish(*args, **kwargs)
    except Exception, err:
        warnings.warn(str(err))


def _clean_emails(emails, user):
    ''' Remove the email of the user doing the action if it is in the list.

    This avoids receiving emails about action you do.
    '''
    # Remove the user doing the action from the list of person to email
    if user and user.emails:
        for email in user.emails:
            if email.email in emails:
                emails.remove(email.email)
    return emails


def _get_emails_for_issue(issue):
    ''' Return the list of emails to send notification to when notifying
    about the specified issue.
    '''
    emails = set()
    # Add project creator/owner
    if issue.project.user.emails:
        emails.add(issue.project.user.emails[0].email)

    # Add project maintainers
    for user in issue.project.users:
        if user.emails:
            emails.add(user.emails[0].email)

    # Add people that commented on the ticket
    for comment in issue.comments:
        if comment.user.emails:
            emails.add(comment.user.emails[0].email)

    # Add the person that opened the issue
    if issue.user.emails:
        emails.add(issue.user.emails[0].email)

    # Add the person assigned to the ticket
    if issue.assignee and issue.assignee.emails:
        emails.add(issue.assignee.emails[0].email)

    return emails


def send_email(text, subject, to_mail, from_mail=None, mail_id=None,
               in_reply_to=None):  # pragma: no cover
    ''' Send an email with the specified information.

    :arg text: the content of the email to send
    :arg subject: the subject of the email
    :arg to_mail: a string representing a list of recipient separated by a
        coma
    :kwarg from_mail: the email address the email is sent from.
        Defaults to nobody@pagure
    :kwarg mail_id: if defined, the header `mail-id` is set with this value
    :kwarg in_reply_to: if defined, the header `In-Reply-To` is set with
        this value

    '''
    if not to_mail:
        return

    msg = MIMEText(text.encode('utf-8'), 'plain', 'utf-8')
    msg['Subject'] = '[Pagure] %s' % subject
    if not from_mail:
        from_email = 'pagure@fedoraproject.org'
    msg['From'] = from_email
    msg['Bcc'] = to_mail.replace(',', ', ')

    if mail_id:
        msg['mail-id'] = mail_id
        msg['Message-Id'] = '<%s>' % mail_id

    if in_reply_to:
        msg['In-Reply-To'] = '<%s>' % in_reply_to

    # Send the message via our own SMTP server, but don't include the
    # envelope header.
    smtp = smtplib.SMTP(pagure.APP.config['SMTP_SERVER'])
    try:
        smtp.sendmail(
            from_email,
            to_mail.split(','),
            msg.as_string())
    except smtplib.SMTPException as err:
        pagure.LOG.exception(err)
    finally:
        smtp.quit()
    return msg


def notify_new_comment(comment, user=None):
    ''' Notify the people following an issue that a new comment was added
    to the issue.
    '''
    text = """
%s added a new comment to an issue you are following.

New comment:

``
%s
``

%s
""" % (
        comment.user.user,
        comment.comment,
        '%s/%s/issue/%s' % (
            pagure.APP.config['APP_URL'],
            comment.issue.project.name,
            comment.issue.id,
        ),
    )
    mail_to = _get_emails_for_issue(comment.issue)
    if comment.user and comment.user.emails:
        mail_to.add(comment.user.emails[0].email)

    mail_to = _clean_emails(mail_to, user)

    send_email(
        text,
        'Update to issue #%s `%s`' % (comment.issue.id, comment.issue.title),
        ','.join(mail_to),
        mail_id=comment.mail_id,
        in_reply_to=comment.issue.mail_id,
    )


def notify_new_issue(issue, user=None):
    ''' Notify the people following a project that a new issue was added
    to it.
    '''
    text = """
%s reported a new issue against the project: `%s` that you are following.

New issue:

``
%s
``

%s
""" % (
        issue.user.user,
        issue.project.name,
        issue.content,
        '%s/%s/issue/%s' % (
            pagure.APP.config['APP_URL'],
            issue.project.name,
            issue.id,
        ),
    )
    mail_to = _get_emails_for_issue(issue)
    mail_to = _clean_emails(mail_to, user)

    send_email(
        text,
        'New issue `%s`' % issue.title,
        ','.join(mail_to),
        mail_id=issue.mail_id,
    )


def notify_assigned_issue(issue, new_assignee, user):
    ''' Notify the people following an issue that the assignee changed.
    '''
    action = 'reset'
    if new_assignee:
        action = 'assigned to `%s`' % new_assignee.user
    text = """
The issue: `%s` of project: `%s` has been %s by %s.

%s
""" % (
        issue.title,
        issue.project.name,
        action,
        user.username,
        '%s/%s/issue/%s' % (
            pagure.APP.config['APP_URL'],
            issue.project.name,
            issue.id,
        ),
    )
    mail_to = _get_emails_for_issue(issue)
    if new_assignee and new_assignee.emails:
        mail_to.add(new_assignee.emails[0].email)

    mail_to = _clean_emails(mail_to, user)

    uid = time.mktime(datetime.datetime.now().timetuple())
    send_email(
        text,
        'Issue `%s` assigned' % issue.title,
        ','.join(mail_to),
        mail_id='%s/assigned/%s' % (issue.mail_id, uid),
        in_reply_to=issue.mail_id,
    )


def notify_new_pull_request(request):
    ''' Notify the people following a project that a new pull-request was
    added to it.
    '''
    text = """
%s opened a new pull-request against the project: `%s` that you are following.

New pull-request:

``
%s
``

%s
""" % (
        request.user.user,
        request.repo.name,
        request.title,
        '%s/%s/request-pull/%s' % (
            pagure.APP.config['APP_URL'],
            request.repo.name,
            request.id,
        ),
    )
    mail_to = set([cmt.user.emails[0].email for cmt in request.comments])
    mail_to.add(request.repo.user.emails[0].email)
    for prouser in request.repo.users:
        if prouser.emails:
            mail_to.add(prouser.emails[0].email)

    send_email(
        text,
        'Pull-Request #%s `%s`' % (request.id, request.title),
        ','.join(mail_to),
        mail_id=request.mail_id,
    )


def notify_merge_pull_request(request, user):
    ''' Notify the people following a project that a pull-request was merged
    in it.
    '''
    text = """
%s merged a pull-request against the project: `%s` that you are following.

Merged pull-request:

``
%s
``

%s
""" % (
        user.username,
        request.repo.name,
        request.title,
        '%s/%s/request-pull/%s' % (
            pagure.APP.config['APP_URL'],
            request.repo.name,
            request.id,
        ),
    )
    mail_to = set([cmt.user.emails[0].email for cmt in request.comments])
    mail_to.add(request.repo.user.emails[0].email)
    for prouser in request.repo.users:
        if prouser.emails:
            mail_to.add(prouser.emails[0].email)

    uid = time.mktime(datetime.datetime.now().timetuple())
    send_email(
        text,
        'Pull-Request #%s `%s`' % (request.id, request.title),
        ','.join(mail_to),
        mail_id='%s/close/%s' % (request.mail_id, uid),
        in_reply_to=request.mail_id,
    )


def notify_cancelled_pull_request(request, user):
    ''' Notify the people following a project that a pull-request was
    cancelled in it.
    '''
    text = """
%s canceled a pull-request against the project: `%s` that you are following.

Cancelled pull-request:

``
%s
``

%s
""" % (
        user.username,
        request.repo.name,
        request.title,
        '%s/%s/request-pull/%s' % (
            pagure.APP.config['APP_URL'],
            request.repo.name,
            request.id,
        ),
    )
    mail_to = set([cmt.user.emails[0].email for cmt in request.comments])
    mail_to.add(request.repo.user.emails[0].email)
    for prouser in request.repo.users:
        if prouser.emails:
            mail_to.add(prouser.emails[0].email)

    uid = time.mktime(datetime.datetime.now().timetuple())
    send_email(
        text,
        'Pull-Request #%s `%s`' % (request.id, request.title),
        ','.join(mail_to),
        mail_id='%s/close/%s' % (request.mail_id, uid),
        in_reply_to=request.mail_id,
    )


def notify_pull_request_comment(comment, user):
    ''' Notify the people following a pull-request that a new comment was
    added to it.
    '''
    text = """
Project: %s

%s commented on the pull-request: `%s` that you are following.

New comment:

``
%s
``

%s
""" % (
        comment.pull_request.repo.name,
        comment.user.user,
        comment.pull_request.title,
        comment.comment,
        '%s/%s/request-pull/%s' % (
            pagure.APP.config['APP_URL'],
            comment.pull_request.repo.name,
            comment.pull_request.id,
        ),
    )
    mail_to = set([
        cmt.user.emails[0].email
        for cmt in comment.pull_request.comments])
    mail_to.add(comment.pull_request.repo.user.emails[0].email)
    for prouser in comment.pull_request.repo.users:
        if prouser.emails:
            mail_to.add(prouser.emails[0].email)

    mail_to = _clean_emails(mail_to, user)

    send_email(
        text,
        'Update to pull-Request #%s `%s`' % (
            comment.pull_request.id, comment.pull_request.title),
        ','.join(mail_to),
        mail_id=comment.mail_id,
        in_reply_to=comment.pull_request.mail_id,
    )


def notify_new_email(email, user):
    ''' Ask the user to confirm to the email belong to them.
    '''

    root_url = pagure.APP.config.get('APPLICATION_URL', flask.request.url_root)

    url = urlparse.urljoin(
        root_url or flask.request.url_root,
        flask.url_for('confirm_email', token=email.token),
    )

    text = """Dear %(username)s,

You have registered a new email on pagure at %(root_url)s.

To finish your validate this registration, please click on the following
link or copy/paste it in your browser, this link will remain valid only 2 days:
  %(url)s

The email will not be activated until you finish this step.

Sincerely,
Your pagure admin.
""" % ({'username': user.username, 'url': url, 'root_url': root_url})

    send_email(
        text,
        'Confirm new email',
        email.email,
    )
