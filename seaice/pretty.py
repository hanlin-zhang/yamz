# pretty.py - Pretty formatting for db table rows. There are routines defined
# here for use in a terminal as well as on the web. 
#
# Copyright (c) 2013, Christopher Patton, all rights reserved.
# 
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#   * Redistributions of source code must retain the above copyright
#     notice, this list of conditions and the following disclaimer.
#   * Redistributions in binary form must reproduce the above copyright
#     notice, this list of conditions and the following disclaimer in the
#     documentation and/or other materials provided with the distribution.
#   * The names of contributors may be used to endorse or promote products
#     derived from this software without specific prior written permission.
# 
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
# ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL <COPYRIGHT HOLDER> BE LIABLE FOR ANY
# DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
# (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
# ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
# SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

import sys, time, datetime
import json, re, string
from dateutil import tz

  ## Some JavaScripts that are embedded into some of the outputs. ##

js_confirmRemoveTerm = """
  function ConfirmRemoveTerm(id) {
    var r=window.confirm("Are you sure you want to delete term #" + id + "?");
    if (r==true) { 
      x=id; 
      var form = document.createElement("form");
      form.setAttribute("method", "post");
      form.setAttribute("action", "/term=" + id + "/remove");
      field = document.createElement("input");
      field.setAttribute("name", "id");
      field.setAttribute("value", id);
      form.appendChild(field);
      document.body.appendChild(form); 
      form.submit();
    } else { x="nil"; } } """

js_confirmRemoveComment = """
  function ConfirmRemoveComment(id) {
    var r=window.confirm("Are you sure you want to your comment?");
    if (r==true) { 
      x=id; 
      var form = document.createElement("form");
      form.setAttribute("method", "post");
      form.setAttribute("action", "/comment=" + id + "/remove");
      field = document.createElement("input");
      field.setAttribute("name", "id");
      field.setAttribute("value", id);
      form.appendChild(field);
      document.body.appendChild(form); 
      form.submit();
    } else { x="nil"; } } """

js_termAction = """
  function TermAction(id, v) {
    var form = document.createElement("form"); 
    form.setAttribute("method", "post");
    if (v == "up" || v == "down") {
      var action = "vote"; 
    } else {
      var action = "track"; 
    }
    form.setAttribute("action", "/term=" + id + "/" + action); 
    field = document.createElement("input"); 
    field.setAttribute("name", "action")
    field.setAttribute("value", v);
    form.appendChild(field);
    document.body.appendChild(form);
    form.submit(); 
  } """

js_copyToClipboard = """
  function CopyToClipboard(text) {
    window.prompt("Hit Ctrl-C (Cmd-C), then Enter to copy this reference to your clipboard. " +
                  "Embedding the reference in your term definition or comment " +
                  "will create a hyperlink to this term.", text);
  }
"""

#: Background color to display with term class. 
colorOf = { 'vernacular' : '#FFFF66', 
            'canonical' : '#3CEB10', 
            'deprecated' : '#E8E8E8' }

#: Name of months. See :func:`seaice.pretty.printPrettyDate`.
monthOf = [ 'January', 'February', 'March', 
            'April', 'May', 'June', 
            'July', 'August', 'September', 
            'October', 'November', 'December' ]
  
# A nice color: A5C6D6
tag_style = '''
style="font-size: 95%;
    font-family: 'Sans-Serif', Arial, serif;
    color:white; background-color:#0082C3;
    border-radius:4px; text-decoration:none"
'''

gtag_style = '''
style="font-size: 85%;
    font-family: 'Sans-Serif', Arial, serif;
    color:blue; background-color:#cceeff;
    border-radius:4px; text-decoration:none"
'''

ref_string = '<a href=/term={0} title="{2}">{1}</a>'
tag_string = '<a href=/tag/{0} ' + tag_style + '>&nbsp;<b>#</b>&nbsp;{1}&nbsp;</a>'
gtag_string = '<a href=/tag/{0} title="{2}" ' + gtag_style + '>&nbsp;{1}&nbsp;</a>'
term_tag_string = '<a href=/term={0} title="{1}">{2}</a>'

# Regular expressions for string matches.
token_ref_regex = re.compile("(?<!#\{g: )([#&]+)([\w.-]+)")
# Caution: exactly one space here -----^
# The "lookbehind" regex relies on _ref_norm using just one space.
# We use it to match #foo NOT inside a #{g:... construct.

#ref_regex = re.compile("#\{\s*(([gstkm])\s*:+)?\s*#*([^}|]*?)(\s*\|+\s*([^}]*?))?\s*\}")
ref_regex = re.compile("#\{\s*(([gstkm])\s*:+)?\s*([^}|]*?)(\s*\|+\s*([^}]*?))?\s*\}")
# subexpr start positions:    01                  2        3         4
#endrefs_regex = re.compile("#\{\s*([gve])\s*:\s*---\s*}\s*")
_xtag_regex = re.compile("#(([a-zA-Z][a-zA-Z0-9_\-\.]*)_term)")	# hack!
#tag_regex = re.compile("#([a-zA-Z][a-zA-Z0-9_\-\.]*[a-zA-Z0-9])")
_xterm_tag_regex = re.compile("#\{\s*([a-zA-Z0-9]+)\s*:\s*(related to[^\{\}]*)\}")	# hack!
#term_tag_regex = re.compile("#\{\s*([a-zA-Z0-9]+)\s*:\s*([^\{\}]*)\}")
permalink_regex = re.compile("^http://(.*)$")

# The "uniquerifier" (ixuniq) makes a tag string uniquer for indexing,
# improving search precision when a user clicks on a tag.  The ixuniq
# string is prepended to a user-defined tag during storage normalization
# and stripped out during display normalization.

ixuniq = '#'
ixqlen = len(ixuniq)

def _token_ref_norm(m):
  """ Promote simple "&ref" into curly "#{t: ref} or, if ref
  begins with "#", into "#{g: ref}".

  :param string: The input string. 
  :returns: Modified plain text string.
  """

  #token = m.group(1)
  #if token.startswith('#'):
  #  return '#{g: ' + token + '}'
  sigil = m.group(1)
  token = m.group(2)
  if sigil == '#':
    return '#{g: ' + ixuniq + token + '}'
  elif sigil == '&':
    return '#{t: ' + token + '}'
  else:
    return sigil + token	# return untouched if doubled

def _xtag_norm(db_con, m):
  """ Promote old style "#xxx_term" into new style "#{g: #xxx | hNNNN }".
  """
  subtag = m.group(2)	# xxx hack, should match "ppsr" in "ppsr_term"
  return '#' + subtag
  #n, term = db_con.getTermByTermString(subtag)
  #if n == 1:
  #  term_string, concept_id = term['term_string'], term['concept_id']
  #elif n == 0:
  #  term_string, concept_id = (subtag + '(undefined)'), '-'
  #elif n == 2:
  #  term_string, concept_id = (subtag + '(ambiguous)'), '-'
  #return '#{g: #%s | %s }' % (term_string, concept_id)

def _xterm_tag_norm(db_con, m):
  """ Promote old style "#{hNNNN : related to}" into new style
  "#{t: term string | hNNNN }".
  """
  concept_id = m.group(1)
  term = db_con.getTermByConceptId(concept_id)
  if term:
    term_string = term['term_string']
  else:
    term_string = concept_id + '(undefined)'

  return '#{t: %s | %s }' % (term_string, concept_id)


def refs_norm(db_con, string, force=False): 
  """ Resolve references in text entries before storing in DB.

  :param db_con: DB connection.
  :type db_con: seaice.SeaIceConnector.SeaIceConnector
  :param string: The input string. 
  :returns: Modified plain text string.
  """

  # xxx temporary transitional hack
  # convert old xterm_tag_regex and xtag_regex matches
  string = _xterm_tag_regex.sub(lambda m: _xterm_tag_norm(db_con, m), string)
  string = _xtag_regex.sub(lambda m: _xtag_norm(db_con, m), string)

  # first promote any simple "#ref" into curly "#{t: ref}
  string = token_ref_regex.sub(lambda m: _token_ref_norm(m), string)
  #string = token_ref_regex.sub('#{t: \\1}', string)
  # now convert each curly "#{reference}
  string = ref_regex.sub(lambda m: _ref_norm(db_con, m, force), string)
  return string
    

# looks a lot like _printRefAsHTML, but is about how we _store_ things
def _ref_norm(db_con, m, force=False): 
  """ Input a regular expression match and output a normalized reference.
  
  A DB connector is required to resolve the tag string by ID. 
  A reference has the form #{ reftype: humstring [ | IDstring ] }
  - reftype is one of
        t (term), g (tag), m (mtype), k (link)
  - humstring is the human-readable equivalent of IDstring
  - IDstring is a machine-readable string, either a concept_id or,
    in the case of "k" link, a URL.
  - the normalized reference will include all three parts
  - normalization is based on looking up the given humstring, but
    that only happens if IDstring is not present or force=True
  - humstring will have "(undefined)" added if lookup fails or
    "(ambiguous)" added if lookup returns more than one hit

  :param db_con: DB connection.
  :type db_con: seaice.SeaIceConnector.SeaIceConnector
  :param m: Regular expression match. 
  :type m: re.MatchObject
  :param force: flag to force humstring lookup
  :type m: boolean
  """

  (rp) = m.groups()	# rp = ref parts, the part between #{ and }
                        # we want subexpressions 1, 2, and 4
  reftype, humstring, IDstring = rp[1], rp[2], rp[4]
  if not reftype:
    reftype = 't'		# apply default reftype
  if not humstring and not IDstring:	# when both are empty
    return '#{}'		# this is all we do for now
  # If we get here, one of them is non-empty.
  if reftype == 'k':		# an external link (URL)
    if humstring and not IDstring:	# assume the caller
      IDstring = humstring		# mixed up the order
    if IDstring and not humstring:	# if no humanstring
      humstring = IDstring	# use link text instead
    return '#{k: %s | %s }' % (humstring, IDstring)

  # If we get here, reftype is not k, and humstring is expected to
  # reference a term_string in the dictionary.  If IDstring is empty or
  # force=True, humstring is looked up in order to resolve it to a unique
  # IDstring (so if IDstring is wrong, delete it or use force=True to
  # correct it).
  # 
  if IDstring and not force:
    return '#{%s: %s | %s}' % (reftype, humstring, IDstring)
  if humstring.startswith('---'):		# reserved magic string
    return '#{%s: %s}' % (reftype, humstring)

  # If we get here, we're going to do the lookup.
  #if reftype == 'g' and not humstring.startswith('#'):
  if reftype == 'g':
    humstring = ixuniq + humstring	# add uniquerifier before storing
  n, term = db_con.getTermByTermString(humstring)
  if n == 1:
    term_string, concept_id = term['term_string'], term['concept_id']
  elif n == 0:
    term_string, concept_id = (humstring + '(undefined)'), '-'
  elif n == 2:
    term_string, concept_id = (humstring + '(ambiguous)'), '-'
  return '#{%s: %s | %s}' % (reftype, term_string, concept_id)
  # this space ^ is relied on by a (fixed width) lookbehind regex


  ## Processing tags in text areas. ##

def _printRefAsHTML(db_con, m): 
  """ Input a regular expression match and output the reference as HTML.
  
  A DB connector is required to resolve the tag string by ID. 
  A reference has the form #{ reftype: humstring [ | IDstring ] }
  - reftype is one of
    t (term), g (tag), s (section), m (mtype), k (link)
    #t (term), g (tag), e (element), v (value), m (mtype), k (link)
  - humstring is the human-readable equivalent of IDstring
  - IDstring is a machine-readable string, either a concept_id or,
    in the case of "k" link, a URL.
  - Note that the reference should have been normalized before being
    stored in the database. (xxx check if that's true for API uploading)

  :param db_con: DB connection.
  :type db_con: seaice.SeaIceConnector.SeaIceConnector
  :param m: Regular expression match. 
  :type m: re.MatchObject
  """

  (rp) = m.groups()	# rp = ref parts, the part between #{ and }
                        # we want subexpressions 1, 2, and 4
  reftype, humstring, IDstring = rp[1], rp[2], rp[4]
  if not reftype:
    reftype = 't'		# apply default reftype
  if not humstring and not IDstring:		# when empty
    return '#{}'		# this is all we do for now
  if reftype == 'k':		# an external link (URL)
    if humstring and not IDstring:	# assume the caller
      IDstring = humstring		# mixed up the order
    if not humstring:		# if no humanstring
      humstring = IDstring	# use link text instead
    if not IDstring.startswith('http:'):
      IDstring = 'http://' + IDstring
    return '<a href="%s">%s</a>' % (IDstring, humstring)

  if humstring.startswith('---'):	# EndRefs
    if humstring.startswith('---e'):
      return '<br>Elements: '
    if humstring.startswith('---v'):
      return '<br>Values: '
    if humstring.startswith('---t'):
      return '<br> '
    #if reftype == 'e':
    #  return '<br>Elements: '
    #if reftype == 'v':
    #  return '<br>Values: '
    #if reftype == 'g':
    #  return '<br> '
    
  # If we get here, reftype is not k, and IDstring (concept_id)
  # is expected to reference a term in the dictionary.
  # 
  term = db_con.getTermByConceptId(IDstring)
  term_def = "Def: " + (term['definition'] if term else "(undefined)")
  # yyy can we improve poor search for '#tag' query?
  if reftype == 'g':
    # yyy in theory don't need to check before removing uniquerifier string
    if humstring.startswith(ixuniq):	# stored index "uniquerifier" string
      humstring = humstring[ixqlen:]	# but remove "uniquerifier" on display
    #if humstring.startswith('#'):	# store as '#tag' for indexing
    #  humstring = humstring[1:]		# but remove '#' on display
    return gtag_string.format(
      string.lower(humstring), humstring, term_def)
  return ref_string.format(IDstring, humstring, term_def)

def _printTagAsHTML(db_con, m): 
  """ Input a regular expression match and output the tag as HTML.
  
  A DB connector is required to resolve the tag string by ID. 

  :param db_con: DB connection.
  :type db_con: seaice.SeaIceConnector.SeaIceConnector
  :param m: Regular expression match. 
  :type m: re.MatchObject
  """
  (tag,) = m.groups()
  return tag_string.format(string.lower(tag), tag)

def _printTermTagAsHTML(db_con, m): 
  """ Input a regular expression match and output the tag as HTML.
  
  A DB connector is required to resolve the term string by ID. 
  If there are syntax errors, simply return the raw tag. 

  :param db_con: DB connection.
  :type db_con: seaice.SeaIceConnector.SeaIceConnector
  :param m: Regular expression match. 
  :type m: re.MatchObject
  """
  (term_concept_id, desc) = m.groups()
  # xxx desc unused
  try:
    #desc = desc.strip().replace('"', '&#34;')
    #term_string = db_con.getTermStringByConceptId(term_concept_id)
    term = db_con.getTermByConceptId(term_concept_id)
    term_string = term['term_string'] if term else term_concept_id
    # xxx isn't this the same code as _printRefAsHTML? should consolidate
    term_def = "Def: " + (term['definition'] if term else "(undefined)")
    return term_tag_string.format(term_concept_id, term_def, term_string)
    #if term_string:
      #return term_tag_string.format(term_concept_id, desc, term_string)
  except: pass
  return m.group(0)


def processTagsAsHTML(db_con, string): 
  """  Process tags in DB text entries into HTML. 

  :param db_con: DB connection.
  :type db_con: seaice.SeaIceConnector.SeaIceConnector
  :param string: The input string. 
  :returns: HTML-formatted string.
  """

  # preserve user-defined newlines by converting to line breaks on output
  # replace tags afterwards (because replacement may add newlines)
  string = string.replace("\n", "\n<br>")

  # xxx transitional code to support old style tags along with new style tags
  # xxx problemmatic!
  string = _xtag_regex.sub(lambda m: _printTagAsHTML(db_con, m), string)
  string = _xterm_tag_regex.sub(lambda m: _printTermTagAsHTML(db_con, m), string)

  string = ref_regex.sub(lambda m: _printRefAsHTML(db_con, m), string)
  string = string.replace("##", "#")	# escape mechanism
  string = string.replace("&&", "&")
  return string


  ## Pretty prints. ##

def printPrettyDate(T):
  """ Format output of a timestamp. 

    If a small amount of time has elapsed between *T_now* 
    and *T*, then return the interval. **TODO:** This should
    be localized based on the HTTP request. 

  :param T: Timestamp. 
  :type T: datetime.datetime
  :rtype: str
  """
  
  T = T.astimezone(tz.tzlocal())
  T_elapsed = (datetime.datetime.now(tz=tz.tzlocal()) - T)

  if T_elapsed < datetime.timedelta(seconds=30):
    return "just now"
  elif T_elapsed < datetime.timedelta(minutes=1):
    return "%s seconds ago" % (T_elapsed.seconds)
  elif T_elapsed < datetime.timedelta(hours=1):
    return "%s minute%s ago" % (T_elapsed.seconds / 60, '' if T_elapsed.seconds / 60 == 1 else 's')
  elif T_elapsed < datetime.timedelta(hours=24):
    return "%s hour%s ago" % (T_elapsed.seconds / 3600, '' if T_elapsed.seconds / 3600 == 1 else 's')
  elif T_elapsed < datetime.timedelta(days=7): 
    return "%s day%s ago" % (T_elapsed.days, '' if T_elapsed.days == 1 else 's')
  else: 
    return "%s %s %s" % (T.day, monthOf[T.month-1], T.year)

def printAsJSObject(rows, fd = sys.stdout):
  """ Print table rows as JSON-formatted object. 

  :param rows: Table rows. 
  :type rows: dict iterator
  :param fd: File descriptor to which to output the result (default is sys.stdout). 
  :type fd: file
  """
  for row in rows:
    for (col, value) in row.iteritems(): 
      if type(value) == datetime.datetime:
        row[col] = str(value)
  print >>fd, json.dumps(rows, sort_keys=True, indent=2, separators=(',', ': '))

def getPrettyParagraph(db_con, text, leftMargin=8, width=60): 
  """ Format some text into a nice paragraph for displaying in the terminal. 
      Output the result directly to sys.stdout. 

  :param db_con: DB connection.
  :type db_con: seaice.SeaIceConnector.SeaIceConnector
  :param text: The paragraph. 
  :type text: str
  :param leftMargin: Number of spaces to print before the start of each line. 
  :type leftMargin: int
  :param width: Number of characters to print per line. 
  :type wdith: int
  """
  lineLength = 0
  fella = " " * (leftMargin-1)
  for word in text.split(" "):
    if lineLength < width:
      fella += word + " " 
      lineLength += len(word) + 1
    else:
      fella += "\n" + (" " * (leftMargin-1))
      lineLength = 0
  return fella

def getPrettyTerm(db_con, row, leftMargin=5):
  """ Return a term string. 

  :param db_con: DB connection.
  :type db_con: seaice.SeaIceConnector.SeaIceConnector
  :param rows: Table rows. 
  :type rows: dict iterator
  """
  text = ' ' * leftMargin + "TERM: %-26s ID: %-7d created: %s\n" % (
     "%s (%d)" % (row['term_string'], row["up"] - row["down"]), row['id'],
     row['created'].strftime('%Y-%m-%d %H:%M:%S'))

  text += ' ' * leftMargin + 'URI: %-40s' % row['persistent_id'] + "Last modified: %s" % (
          row['modified'].strftime('%Y-%m-%d %H:%M:%S'))

  text += "\n\n"
  text += getPrettyParagraph(db_con, "DEFINITION: " + row['definition'])
  
  text += "\n\n"
  text += getPrettyParagraph(db_con, "EXAMPLES: " + row['examples'])
            
  #text += "\n    Ownership: %s" % db_con.getUserNameById(row['owner_id'])
  return text

def getPrettyComment(db_con, row, leftMargin=5): 
  """ Return a comment string.

  :param db_con: DB connection.
  :type db_con: seaice.SeaIceConnector.SeaIceConnector
  :param rows: Table rows. 
  :type rows: dict iterator
  """
  return 'yeah'

def printTermsPretty(db_con, rows):
  """ Print term rows to terminal. 

  :param db_con: DB connection.
  :type db_con: seaice.SeaIceConnector.SeaIceConnector
  :param rows: Table rows. 
  :type rows: dict iterator
  """
  for row in rows:
    print getPrettyTerm(db_con, row) 



def printTermsAsLinks(rows):
  """ Print terms as a link list (pun intended). 

  :param rows: Table rows. 
  :type rows: dict iterator
  :returns: HTML-formatted string. 
  """
  string = ""
  for row in rows: 
    string += '<li><a href="/term=%s">%s</a></li>' % (row['concept_id'], row['term_string'])
  return string

def printTermAsHTML(db_con, row, user_id=0):
  """ Format a term for the term page, e.g. `this <http://seaice.herokuapp.com/term=1001>`_.

    This is the main page where you can look at a term. It includes a term definition, 
    examples, a voting form, ownership, and other stuff.  

  :param db_con: DB connection.
  :type db_con: seaice.SeaIceConnector.SeaIceConnector
  :param row: Term row. 
  :type row: dict
  :param user_id: Surrogate ID of user requesting the page. Defaults to 0 if session is 
                  unauthenticated. 
  :type user_id: int 
  :returns: HTML-formatted string.
  """

  vote = db_con.getVote(0 if not user_id else user_id, row['id'])
  string = '<script>' + js_confirmRemoveTerm + js_termAction + js_copyToClipboard + '</script>'

  # Voting
  string += '<table>' 
  string += "  <tr><td width=150px rowspan=4 align=center valign=top>"
  string += '    <a id="voteUp" title="+1" href="#up" onclick="return TermAction(%s, \'up\');">' % row['id']
  string += '     <img src="/static/img/%s.png"></a><br>' % ('up_set' if vote == 1 else 'up')

  string += '    <h4>'
  if row['up'] > 0:
    string += '    <font color="#004d73">+%s</font> &nbsp;' % row['up']
  if row['down'] > 0: 
    string += '    <font color="#797979">-%s</font>' % row['down']
  if row['up'] == 0 and row['down'] == 0:
    string += '0'
  string += '    </h4>'

  string += '    <a id="voteDown" title="-1" href="#down" onclick="return TermAction(%s, \'down\');">' % row['id']
  string += '     <img src="/static/img/%s.png"></a><br>' % ('down_set' if vote == -1 else 'down')
  
  
  good = db_con.checkTracking(0 if not user_id else user_id, row['id'])
  string += '    <br><a id="star" title="Track this term" href="#star"' + \
            '     onclick="return TermAction({1}, \'{0}\');">[{2}]</a><br> '.format(
             ("unstar" if good else "star"), row['id'], 'unwatch' if good else 'watch')
  string += "  </td></tr>"

  termstr = '''<a id="copyLink" title="Click to get a reference link to this term."
                  href="#" onclick="CopyToClipboard('#{t: %s | %s}');"
               ><font size=\"3\"><strong>%s</strong></font></a>''' % (
	         row['term_string'], row['concept_id'], row['term_string'])

  # Name/Class
  string += "  <tr>"
  string += "    <td valign=top width=8%><i>Term:</i></td>"
  #string += "    <td valign=top width=25%><font size=\"3\"><strong>{0}</strong></font><td>".format(row['term_string']) 
  string += "    <td valign=top width=25%>{0}<td>".format(termstr)
  string += "    <td valign=top width=5% rowspan=2>"
  string += "      <nobr><i>Class:&nbsp;&nbsp;</i></nobr><br>"
  string += "    </td>"
  string += "    <td valign=top width=16% rowspan=2>"
  string += '      <nobr><font style="background-color:{2};border-radius:4px;">&nbsp;{0}&nbsp;</font> <i>&nbsp;({1}%)</i></nobr><br>'.format(
              row['class'], int(100 * row['consensus']), colorOf[row['class']])
  string += "    </td>"

  # Retrieve persistent_id
  term_persistent_id = row['persistent_id']
  if term_persistent_id is None:
      persistent_id = ''
      permalink = ''
  else:
      persistent_id = term_persistent_id
      permalink = permalink_regex.search(persistent_id).groups(0)[0]

  # Created/modified/Owner 
  string += "    <td valign=top width=20% rowspan=3>"
  string += "      <nobr><i>Created %s</i></nobr><br>" % printPrettyDate(row['created'])
  string += "      <nobr><i>Last modified %s</i></nobr><br>" % printPrettyDate(row['modified'])
  string += "      <nobr><i>Contributed by</i> %s</nobr><br>"% db_con.getUserNameById(row['owner_id'], full=True)
  if persistent_id != '':
      string += "      <br>"
      string += '      <nobr><i>Permalink:</i><br>&nbsp;&nbsp;' + permalink + '</nobr><br>'
  if user_id == row['owner_id']:
    string += "    <br><a href=\"/term=%s/edit\">[edit]</a>" % row['concept_id']
    string += """  <a id="removeTerm" title="Click to delete term" href="#"
                   onclick="return ConfirmRemoveTerm(%s);">[remove]</a><br>""" % row['id']
 
  ## Copy reference tag
  #string += '''    <hr><a id="copyLink" title="Click to get a reference link to this term." href="#"
  #                      onclick="CopyToClipboard('#{t: %s | %s}');">Get term link</a>''' % (row['term_string'], row['concept_id'])

  string += "    </td>"
  string += "  </tr>"

  # Definition/Examples
  string += "  <tr>"
  string += "    <td valign=top><i>Definition:</i></td>"
  string += "    <td colspan=4 valign=top style='padding-right:36px'><font size=\"3\"> %s</font></td>" % processTagsAsHTML(db_con, row['definition'])
  string += "  </tr>"
  string += "  <tr>"
  string += "    <td valign=top><i>Examples:</i></td>"
  string += "    <td colspan=4 valign=top style='padding-right:36px'><font size=\"3\"> %s</font></td>" % processTagsAsHTML(db_con, row['examples'])
  string += "  </tr>"
  string += "</table>"
  return string

# xxx not called right now -- needed?
def printTermsAsHTML(db_con, rows, user_id=0): 
  """ Format search results for display on the web page. 
  
  :param db_con: DB connection.
  :type db_con: seaice.SeaIceConnector.SeaIceConnector
  :param row: Term rows. 
  :type row: dict iterator
  :param user_id: Surrogate ID of user requesting the page. Defaults to 0 if session is 
                  unauthenticated. 
  :type user_id: int 
  :returns: HTML-formatted string.
  """
  
  string = '<script>' + js_confirmRemoveTerm + '</script><table>'
  for row in rows:
    string += "  <tr>"
    string += "    <td valign=top width=75%><i>Term:</i>"
    string += "     <font size=\"3\"><strong>{0}</strong></font>".format(row['term_string'])
    string += "      <a href=\"/term=%s\">[view]</a>" % row['concept_id']
    if user_id == row['owner_id']:
      string += "    <a href=\"/term=%s/edit\">[edit]</a>" % row['concept_id']
      string += """  <a id="removeTerm" title="Click to delete term" href="#"
                     onclick="return ConfirmRemoveTerm(%s);">[remove]</a>""" % row['id']
    string += '      &nbsp;<i>Class:</i>&nbsp;<font style="background-color:{2}">&nbsp;{0}&nbsp;</font> <i>&nbsp;({1}%)</i>'.format(
                 row['class'], int(100 * row['consensus']), colorOf[row['class']])
    string += "    </td>" 
    string += "    <td valign=top rowspan=2>"
    string += "      <nobr><i>Created %s</i></nobr><br>" % printPrettyDate(row['created'])
    string += "      <nobr><i>Last modified %s</i></nobr><br>" % printPrettyDate(row['modified'])
    string += "      <nobr><i>Contributed by</i> %s</nobr><br>" % db_con.getUserNameById(row['owner_id'], full=True)
    string += "    </td>"
    string += "  </tr>"
    string += "  <tr>"
    string += "    <td valign=top>"
    string += "     <i>Definition:</i>&nbsp;<font size=\"3\"> %s</font>&nbsp;" % processTagsAsHTML(db_con, row['definition'])
    string += "     <i>Examples:</i>&nbsp;<font size=\"3\"> %s</font></td>" % processTagsAsHTML(db_con, row['examples'])
    string += "  </tr>"
    string += "  <tr height=16><td></td></tr>"
  string += "</table>"
  return string

def summarizeConsensus(consensus):
    """
    Return 'high', 'medium' or 'low' as a rough indicator of consensus.
    """
    cons = int(100 * consensus)
    if cons >= 70:
        return 'high'
    elif cons >= 30:
        return 'medium'
    else:
	return 'low'

def printTermsAsBriefHTML(db_con, rows, user_id=0): 
  """ Format table rows as abbreviated HTML table, e.g. 
      `this <http://seaice.herokuapp.com/browse/volatile>`_.
  
  :param db_con: DB connection.
  :type db_con: seaice.SeaIceConnector.SeaIceConnector
  :param row: Term rows. 
  :type row: dict iterator
  :param user_id: Surrogate ID of user requesting the page. Defaults to 0 if session is 
                  unauthenticated. 
  :type user_id: int 
  :returns: HTML-formatted string.
  """

  string =  '<table width=70%>'
  string += '''<tr style="background-color:#E8E8E8"><td>Term</td>
                  <td>Score</td><td>Consensus</td><td>Class</td><td>Contributed by</td>
                  <td>Last modified</td></tr>'''
  for row in rows:
    string += '''<tr><td><a title="Def: {8}" href=/term={5}>{0}</a></td><td>{1}</td><td>{2}</td>
                     <td><font style="background-color:{6}">&nbsp;{3}&nbsp;</font></td>
                     <td>{4}</td>
                     <td>{7}</tr>'''.format(
          row['term_string'],
          row['up'] - row['down'],
          summarizeConsensus(row['consensus']),
          row['class'], 
          db_con.getUserNameById(row['owner_id'], full=True),
          row['concept_id'],
          colorOf[row['class']],
          printPrettyDate(row['modified']),
	  row['definition'])
  string += "</table>"
  return string

def printCommentsAsHTML(db_con, rows, user_id=0): 
  """ Format comments for display on the term page. 

  :param db_con: DB connection.
  :type db_con: seaice.SeaIceConnector.SeaIceConnector
  :param row: Comment rows. 
  :type row: dict iterator
  :param user_id: Surrogate ID of user requesting the page. Defaults to 0 if session is 
                  unauthenticated. 
  :type user_id: int 
  :returns: HTML-formatted string.
  """

  string = '<script>' + js_confirmRemoveComment + '</script><table>'
  for row in rows:
    string += "<tr>"
    string += "  <td align=left valign=top width=70%>{0}".format(processTagsAsHTML(db_con, row['comment_string']))
    if user_id == row['owner_id']:
      string += " <nobr><a href=\"/comment=%d/edit\">[edit]</a>" % row['id']
      string += """ <a id="removeComment" title="Click to remove this comment" href="#"
                    onclick="return ConfirmRemoveComment(%s);">[remove]</a></nobr>""" % row['id']
    string += "  </td>"
    string += "  <td align=right valign=top><font color=\"#B8B8B8\"><i>Submitted {0}<br>by {1}</i></font></td>".format(
      printPrettyDate(row['created']), db_con.getUserNameById(row['owner_id']))
    string += "</tr>" 
    string += "</tr><tr height=16><td></td></tr>"
  string += "</table>"
  return string
