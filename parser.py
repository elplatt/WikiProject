# -*- coding: utf-8 -*-
# Parse cached Wikipedia assesment logs, output utf-8 encoded TSV

import calendar
from datetime import datetime
from dateutil.parser import parse
import logging
import os
import re
import shutil
import subprocess
import sys
import traceback
import urllib

from bs4 import BeautifulSoup
from bs4 import element

# Config
project_tsv = "data/projects-2016-10-12.utf-16-le.tsv"
project_log = "output/projects/%s/parse.log"
cache_dir = "output/projects/%s/cache"
cache_tar = "output/projects_crawled/%s-cache.tgz"
to_parse = "output/to_parse/%s"
done_parse = "output/done_parse/%s"
assessment_file = "output/assessments/%s.utf8.tsv"
end_timestamp = 1449100800 # 2015-12-03T00:00:00Z

# Test config
test_only = False
test_project = "test"

# Main log
logger = logging.getLogger('parser_main')
handler = logging.FileHandler('output/parser_%s.log' % datetime.now().strftime("%m%dT%H%M"))
logger.addHandler(handler)
logger.setLevel(logging.DEBUG)

# Fields
columns = [
    'Project', 'Date', 'Action', 'ArticleName', 'OldQual',
    'NewQual', 'OldImp', 'NewImp', 'NewArticleName', 'OldArticleLink',
    'OldTalkLink'
]

# Continuation message
contd_text = "This log entry was truncated because it was too long. This entry is a continuation of the entry in the next revision of this log page."

# Regular expressions
date_pattern = re.compile(
    "(January|February|March|April|May|June|July|August|September|October|November|December)"
    "\_\d{1,2}\.2C_\d{4}")
cache_re = re.compile(
    "oldid=(\d+)\.html"
)
assessed_re = re.compile(
    "(.+) \(.+\) assessed."
)
assessed_talkafter_re = re.compile(
    "([^()]+) assessed\."
)
assessed_qual_re = re.compile(
    "Quality assessed as (.+?) \(.+?\)\."
)
assessed_imp_re = re.compile(
    "Importance assessed as (.+?) \(.+?\)\."
)
reassessed_simple_re = re.compile(
    "(.+) reassessed from (.+) \((.+)\) to (.+)\s*\((.+)\)"
)
reassessed_ga_re = re.compile(
    "(.+) upgraded to good article status"
)
reassessed_notalk_re = re.compile(
    "(.+) reassessed\..+\([^()]* t\)\."
)
reassessed_re = re.compile(
    "(.+) \(talk\) reassessed\."
)
reassessed_qual_re = re.compile(
    "Quality rating changed from (\S+) to (\S+)"
)
reassessed_imp_re = re.compile(
    "Importance rating changed from (\S+) to (\S+)"
)
reassessed_quote_rev_re = re.compile(
    "(.+) rev"
)
reassessed_quote_t_re = re.compile(
    "(.+) t"
)
reassessed_moved_re = re.compile(
    "(.+) moved from (.+) \((.+)\) to (.+) \((.+)\)"
)
reassessed_moved_simple_re = re.compile(
    "(.+) moved from (.+) to (.+)"
)
added_simple_re = re.compile(
    "(.+) \([^()]*talk[^()]*\) added"
)
added_re = re.compile(
    "(.+) \([^()]*(?:\([^()]*\))[^()]*[tT]alk[^()]*\) (\S+) \((\S+)\) added"
)
created_re = re.compile(
    "(.+) \([^()]*[tT]alk[^()]*\) Created"
)
recreated_re = re.compile(
    "(.+) \([^()]*[tT]alk[^()]*\) (\S+-Class) recreated"
)
removed_simple_re = re.compile(
    "(.*)\s*\([^()]*talk[^()]*\) (.+) \((.+)\)\s*removed"
)
removed_notalk_re = re.compile(
    "([^()]+) removed\."
)
removed_notalk_assessment_re = re.compile(
    "([^()]+) (\S+-Class) \(([^()]+-Class)\) removed\."
)
removed_re = re.compile(
    "(.+) \([^()]*talk[^()]*\)\s*removed"
)
removed_paren_re = re.compile(
    "(.+) \([^()]*\([^()]*\)[^()]*talk[^()]*\)\s*removed"
)
renamed_simple_re = re.compile(
    "(.+) renamed to (.+)\."
)
removed_pertalk_re = re.compile(
    "(.+) Removed per talk page discussion"
)
renamed_talk_notalk_re = re.compile(
    "([^()]+) \([^()]*[tT]alk[^()]*\) (\S+-Class) \((\S+-Class)\) renamed to (.+)"
)
renamed_talk_re = re.compile(
    "(.+) \([^()]*talk[^()]*\) (.+) \((.+)\) renamed to (.+)"
)
renamed_simple_talk_re = re.compile(
    "(.+) \([^()]*[tT]alk[^()]*(?:\([^()]*\)[^()]*)?\) renamed to " +
    "(.+) \([^()]*[tT]alk[^()]*(?:\([^()]*\)[^()]*)?\)"
)
renamed_re = re.compile(
    "(.+) \(.+?\) (.+) \((.+)\) renamed to (.+)"
)
renamed_assessment_re = re.compile(
    "(.+) \((.+)\)"
)
renamed_moved_talk_re = re.compile(
    "(.+) ([^()]*talk[^()]*) moved to (.+) ([^()]*talk[^()]*)"
)
talk_re = re.compile(
    "[^()]*talk[^()]*"
)
noaction_re = re.compile (
    "(.+) \([^()]*talk[^()]*\) (.+) \((.+)\)"
)
noname_re = re.compile (
    "\([^()]*[tT]alk[^()]*\)"
)
testing_re = re.compile(
    "Temp bot"
)
nochange_re = re.compile(
    "\(No changes today\)"
)
# One-off bot bugs and human edits
to_skip = set([
    "The Cambridge Declaration assessed- Class (Mid)"
    , "Giovanni Sala ([[Talk:Giovanni S"
    , "Mubarak Al-Sabah (talk) Reassessment Needed from Stub Class."
    , "[[Ground Zero (2007 film) [1]]] ([[Talk:Ground Zero (2007 film) [2]|talk]]) Stub-Class (Low-Class) removed."
    , "Foie gras, added with class=GA"
    , "Flag of Ecuador cleaned-up, abridged and wikified Kevin McE 01:19, 22 December 2006 (UTC)"
    , "Achaemenid Empire Still rated as Stub, unassesed"
    , "NASRIYAUnassessed-Class (No-Class) added"
    , "& moved back. No reason for the above undiscussed page move, even the edit summary didn't give any reason. Compare prior discussion at Wikipedia talk:Naming conventions (books)#Article title length."
    , "Songkhla Lake (talk) Mori Riyo added"
    , "Thomas Viaduct (talk) - Complete overhaul, new content added more images added."
    , u"Šumamice Memomial Pamk menamed to Octobem in Kmagujevac Memomial Pamk."
    , "Upstate New York r"
    , "[[M*A*S*H (novels)]] ([[Talk:M*A*S*H (novels)|talk]]) added, as Unassessed (No-Class)"
    , u"Vic and Sade - removed, good article but does not fit this project"
    , u"Human chorionic gonadotropin (Talk:Human chorionic gonadotropin|talk) assessed. Quality assessed as Start-Class (rev ·Importance assessed as Mid-Class (rev · t)."
    , "Statelessness (talk) Unassessed added"
    , "Coca-Cola Refreshing Filmmaker's Award requesting first assessment"
    , "[[Urban Gothic (TV series) [1]]] ([[Talk:Urban Gothic (TV series) [2]|talk]]) Unassessed-Class (No-Class) removed."
    , "Directed_evolution_(transhumanism) (talk)"
    , "Wikipedia is a fake sorry to break it to u people"
    , "Franconia (wine region) (talk) started new article"
    , "Hong Kong (talk) Should be either Top or High (Hong Kong has approx. 7 million people and Asia's World City"
    , "Hong Kong (talk) Should be either Top or High (Hong Kong has approx. 7 million people and China's World City"
])
def get_entry(project_name, date, item, logger):
    text = item.get_text()
    action = ""
    old_qual = ""
    new_qual = ""
    old_imp = ""
    new_imp = ""
    article_name = ""
    article_new_name = ""
    article_old_link = ""
    talk_old_link = ""
    
    m = re.match(reassessed_re, text)
    if m:
        action = "Reassessed"
        article_name, = m.groups()
        m = re.search(reassessed_qual_re, text)
        if m:
            old_qual, new_qual = m.groups()
        m = re.search(reassessed_imp_re, text)
        if m:
            old_imp, new_imp = m.groups()
            
        # Get old revision link
        # Below code still has quoting errors
        # Example from oldid=397973473
        # "Gypsy" in Jazz (Teddy Wilson album) (talk) reassessed. Importance rating changed from Unknown-Class to Mid-Class ("Gypsy"%20in%20Jazz%20%28Teddy%20Wilson%20album%29&oldid=392798701 rev · "Gypsy"%20in%20Jazz%20%28Teddy%20Wilson%20album%29&oldid=397522420 t).
        #try:
        #    rev = item.find('a', text="rev")
        #    article_old_link = rev.get('href').split("?")[1]
        #except AttributeError:
        #    # Couldn't parse, check whether it's a quoting problem
        #    try:
        #        rev = item.find('a', text=reassessed_quote_rev_re)
        #        text_part = re.match(reassessed_quote_rev_re, rev.get_text()).groups()[0]
        #        href_part = rev.get('href').split("?")[1]
        #        article_old_link = href_part + text_part.replace('"', "%22")
        #    except AttributeError:
        #        logger.error("  Couldn't parse: %s" % item.get_text())
        #        raise AssertionError
        # Get old talk link
        #try:
        #    t = item.find('a', text="t")
        #    talk_old_link = t.get('href').split("?")[1]
        #except AttributeError:
        #    # Couldn't parse, check whether it's a quoting problem
        #    try:
        #        t = item.find('a', text=reassessed_quote_t_re)
        #        text_part = re.match(reassessed_quote_t_re, t.get_text()).groups()[0]
        #        href_part = t.get('href').split("?")[1]
        #        talk_old_link = href_part + text_part.replace('"', "%22")
        #    except AttributeError:
        #        logger.error("  Couldn't parse: %s" % item.get_text())
        #        raise AssertionError
        
        # We made it, somehow
        return [
            project_name, date, action, article_name, old_qual, new_qual,
            old_imp, new_imp, article_new_name, article_old_link, talk_old_link]
    
    m = re.match(reassessed_notalk_re, text)
    if m:
        action = "Reassessed"
        article_name, = m.groups()
        m = re.search(reassessed_qual_re, text)
        if m:
            old_qual, new_qual = m.groups()
        m = re.search(reassessed_imp_re, text)
        if m:
            old_imp, new_imp = m.groups()
        # Should also get revision and talk link but don't need it now
        return [
            project_name, date, action, article_name, old_qual, new_qual,
            old_imp, new_imp, article_new_name, article_old_link, talk_old_link]
    
    m = re.match(reassessed_simple_re, text)
    if m:
        action = "Reassessed"
        text.replace("start-class(", "Start-Class (")
        article_name, old_qual, old_imp, new_qual, new_imp = m.groups()
        return [
            project_name, date, action, article_name, old_qual, new_qual,
            old_imp, new_imp, article_new_name, article_old_link, talk_old_link]
    
    try:
        m = re.match(assessed_re, text)
        if m:
            action = "Assessed"
            links = item.find_all('a')
            article_name = links[0].get_text()
            qual_m = re.search(assessed_qual_re, text)
            if qual_m:
                new_qual, = qual_m.groups()
            imp_m = re.search(assessed_imp_re, text)
            if imp_m:
                new_imp, = imp_m.groups()
            # There will be data for revision and talk links
            # but this part of the parser hasn't been implemented yet
            return [
                project_name, date, action, article_name, old_qual, new_qual,
                old_imp, new_imp, article_new_name, article_old_link, talk_old_link]
    except IndexError:
        pass
    
    m = re.match(assessed_talkafter_re, text)
    if m:
        action = "Assessed"
        links = item.find_all('a')
        article_name = links[0].get_text()
        text.replace("Stub -Class", "Stub-Class")
        qual_m = re.search(assessed_qual_re, text)
        if qual_m:
            new_qual, = qual_m.groups()
        imp_m = re.search(assessed_imp_re, text)
        if imp_m:
            new_imp, = imp_m.groups()
        # There will be data for revision and talk links
        # but this part of the parser hasn't been implemented yet
        return [
            project_name, date, action, article_name, old_qual, new_qual,
            old_imp, new_imp, article_new_name, article_old_link, talk_old_link]
    
    m = re.match(renamed_talk_re, text)
    if m:
        action = "Renamed"
        article_name, old_class, old_imp, article_new_name = m.groups()
        return [
            project_name, date, action, article_name, old_qual, new_qual,
            old_imp, new_imp, article_new_name, article_old_link, talk_old_link]
        
    m = re.match(renamed_talk_notalk_re, text)
    if m:
        action = "Renamed"
        article_name, old_class, old_imp, article_new_name = m.groups()
        return [
            project_name, date, action, article_name, old_qual, new_qual,
            old_imp, new_imp, article_new_name, article_old_link, talk_old_link]
    
    m = re.match(renamed_re, text)
    if m:
        links = item.find_all('a')
        # Get article names and talk link
        # Can't trust regex because of nested parentheses
        # Instead trim links from ends of string
        action = "Renamed"
        article_name = links[0].get_text()
        if len(links) == 2:
            article_new_name = links[1].get_text()
            if re.match(talk_re, article_new_name):
                logger.error("Unable to find new name: %s" % text)
                raise ValueError
        elif len(links) > 2:
            article_new_name = links[2].get_text()
            if re.match(talk_re, article_new_name):
                logger.error("Unable to find new name: %s" % text)
                raise ValueError
            # Was attempt to capture assessment
            # Ignore for now since this is a rename
            #front = len(article_name) + len(talk_text) + len(" () ")
            #back = len(article_new_name) + len(" ")
            #assessment_part = text[front:-back]
            #try:
            #    old_class, old_imp = re.match(renamed_assessment_re, assessment_part).groups()
            #except AttributeError:
            #    logger.error("  Unable to parse old assessment: %s" % assessment_part)
            #    raise ValueError
        else:
            logger.error("renamed_re unrecognized link count")
            raise ValueError
        return [
            project_name, date, action, article_name, old_qual, new_qual,
            old_imp, new_imp, article_new_name, article_old_link, talk_old_link]
    
    m = re.match(renamed_simple_talk_re, text)
    if m:
        action = "Renamed"
        article_name, article_new_name = m.groups()
        # We should capture talk, ignoring for now
        return [
            project_name, date, action, article_name, old_qual, new_qual,
            old_imp, new_imp, article_new_name, article_old_link, talk_old_link]    
    
    m = re.match(renamed_simple_re, text)
    if m:
        action = "Renamed"
        article_name, article_new_name = m.groups()
        return [
            project_name, date, action, article_name, old_qual, new_qual,
            old_imp, new_imp, article_new_name, article_old_link, talk_old_link]
    
    m = re.match(renamed_moved_talk_re, text)
    if m:
        action = "Renamed"
        article_name, article_new_name = m.groups()
        return [
            project_name, date, action, article_name, old_qual, new_qual,
            old_imp, new_imp, article_new_name, article_old_link, talk_old_link]
    
    m = re.match(added_re, text)
    if m:
        action = "Assessed"
        article_name, new_qual, new_imp = m.groups()
        # Some articles have leftover wiki markup around the title, remove
        article_name = article_name.strip("[]")
        return [
            project_name, date, action, article_name, old_qual, new_qual,
            old_imp, new_imp, article_new_name, article_old_link, talk_old_link]
    
    m = re.match(added_simple_re, text)
    if m:
        action = "Assessed"
        article_name, = m.groups()
        return [
            project_name, date, action, article_name, old_qual, new_qual,
            old_imp, new_imp, article_new_name, article_old_link, talk_old_link]
    
    m = re.match(created_re, text)
    if m:
        action = "Assessed"
        article_name, = m.groups()
        return [
            project_name, date, action, article_name, old_qual, new_qual,
            old_imp, new_imp, article_new_name, article_old_link, talk_old_link]
    
    m = re.match(recreated_re, text)
    if m:
        action = "Assessed"
        article_name, new_qual = m.groups()
        return [
            project_name, date, action, article_name, old_qual, new_qual,
            old_imp, new_imp, article_new_name, article_old_link, talk_old_link]
    
    m = re.match(removed_re, text)
    if m:
        action = "Removed"
        article_name, = m.groups()
        return [
            project_name, date, action, article_name, old_qual, new_qual,
            old_imp, new_imp, article_new_name, article_old_link, talk_old_link]
    
    m = re.match(removed_simple_re, text)
    if m:
        action = "Removed"
        article_name, old_class, old_imp = m.groups()
        if article_name == "":
            # Some entries have no article name, weird. Skip them.
            raise StopIteration
        return [
            project_name, date, action, article_name, old_qual, new_qual,
            old_imp, new_imp, article_new_name, article_old_link, talk_old_link]
    
    m = re.match(removed_notalk_assessment_re, text)
    if m:
        action = "Removed"
        article_name, old_class, old_imp = m.groups()
        return [
            project_name, date, action, article_name, old_qual, new_qual,
            old_imp, new_imp, article_new_name, article_old_link, talk_old_link]

    m = re.match(removed_paren_re, text)
    if m:
        action = "Removed"
        article_name, = m.groups()
        return [
            project_name, date, action, article_name, old_qual, new_qual,
            old_imp, new_imp, article_new_name, article_old_link, talk_old_link]

    m = re.match(removed_notalk_re, text)
    if m:
        action = "Removed"
        article_name, = m.groups()
        return [
            project_name, date, action, article_name, old_qual, new_qual,
            old_imp, new_imp, article_new_name, article_old_link, talk_old_link]
    
    m = re.match(removed_pertalk_re, text)
    if m:
        action = "Removed"
        article_name, = m.groups()
        return [
            project_name, date, action, article_name, old_qual, new_qual,
            old_imp, new_imp, article_new_name, article_old_link, talk_old_link]

    m = re.match(reassessed_moved_re, text)
    if m:
        action = "Reassessed"
        article_name, old_qual, old_imp, new_qual, new_imp = m.groups()
        return [
            project_name, date, action, article_name, old_qual, new_qual,
            old_imp, new_imp, article_new_name, article_old_link, talk_old_link]

    m = re.match(reassessed_moved_simple_re, text)
    if m:
        action = "Reassessed"
        article_name, old_qual, new_qual = m.groups()
        return [
            project_name, date, action, article_name, old_qual, new_qual,
            old_imp, new_imp, article_new_name, article_old_link, talk_old_link]

    m = re.match(reassessed_ga_re, text)
    if m:
        action = "Reassessed"
        article_name, = m.groups()
        new_qual = "GA-Class"
        return [
            project_name, date, action, article_name, old_qual, new_qual,
            old_imp, new_imp, article_new_name, article_old_link, talk_old_link]

    m = re.match(testing_re, text)
    if m:
        # We've found testing code, ignore it
        raise StopIteration

    m = re.match(noaction_re, text)
    if m:
        # Some entries have no action, probably bug in bot
        raise StopIteration

    m = re.match(noname_re, text)
    if m:
        # No article name, probably bug in bot, skip
        raise StopIteration

    m = re.match(nochange_re, text)
    if m:
        # No change, skip
        raise StopIteration

    if text[0] == "^":
        # Weirdness in project: New York City
        raise StopIteration

    # One-time bugs
    if text in to_skip:
        raise StopIteration

    # Check for entries that are just an article name, skip
    links = item.find_all('a')
    if len(links) == 1 and links[0].get_text() == text:
        raise StopIteration

    logger.error("Unrecognized format: <<%s>>" % text)
    raise ValueError

def parse_date(date_string):
    '''Convert date_string (assumed UTC) to UTC timestamp.'''
    fmt1 = "%B %d, %Y"
    fmt2 = "%Y-%m-%d"    
    try:
        try:
            dt = datetime.strptime(date_string, fmt1)
        except ValueError:
            dt = datetime.strptime(date_string, fmt2)
    except ValueError:
        raise ValueError
    try:
        timestamp = calendar.timegm(dt.timetuple())
    except TypeError:
        raise ValueError
    return timestamp

def parse(project_name):
    clean_name = project_name.replace("/", "_")
    logger = logging.getLogger(project_name)
    fh = logging.FileHandler(project_log % clean_name)
    logger.addHandler(fh)
    logger.setLevel(logging.DEBUG)
    logger.info("Beggining parse")
    
    entries = {}
    
    # Loop through cached history pages
    # Go newest to oldest for correct order in multi-page entries
    pages = os.listdir(cache_dir % clean_name)    
    pages = sorted(os.listdir(cache_dir % clean_name), reverse=True)
    page_ids = [int(re.match(cache_re, page).groups()[0]) for page in pages]
    page_ids = sorted(page_ids, reverse=True)
    for i, page in enumerate(page_ids):
        if i > 0 and i % 100 == 0:
            print "%d: %2.2f%%" % (i, (float(100*i) / float(len(pages))))
        # Load html into beautifulsoup
        with open(os.path.join(cache_dir % clean_name, "oldid=%d.html" % page)) as f:
            page_tree = BeautifulSoup(f.read(), 'html.parser')
        try:
            # Prevent running out of filehandlers if python procrastinates
            f.close()
        except:
            pass
        
        # Check whether this page is a continuation
        p = page_tree.find(text=contd_text)
        # If not, find the first date header
        if p is None:
            contd = False
            try:
                header_tags = page_tree.find_all("h3")
                date_tags = [x for x in header_tags
                                if x.span and x.span.get('class') == ["mw-headline"]
                                    and 'id' in x.span.attrs
                                    and date_pattern.match(x.span.get('id'))]
                try:
                    current_tag = date_tags[0]
                except IndexError:
                    logger.info("No headers match pattern: %s" % page)
                    continue
            except Exception as TagNotFoundException:
                logger.info("No headers found: %s" % page)
                continue
            try:
                date_text = current_tag.span.get_text()
                current_date = parse_date(date_text)
            except ValueError:
                logger.error("Unable to parse date: %s" % str(current_tag))
                raise
        else:
            contd = True
            try:
                logger.info("  Continuing date: %d" % current_date)
            except UnboundLocalError:
                # Crawl stopped in the middle of multi-page entry
                # Just skip to the first full entry
                continue
            current_tag = page_tree.find(id="mw-content-text").find('ul')

        entry_count = 0
        skip_count = 0
        while True:
            # Move to next tag
            # If we're continuing from the last page, we're already on the right
            # tag so we don't go to the next one.
            if contd:
                contd = False
            else:
                try:
                    current_tag = current_tag.next_sibling
                    current_tag.name
                except AttributeError:
                    if entry_count == 0 and skip_count == 0:
                        huge = page_tree.find(text="The log for today is too huge to upload to the wiki.")
                        if huge is None:
                            logger.error("Found no entries in: %s" % page)
                        else:
                            logger.warning("Log too large to upload: %s" % page)
                    #logger.info("  Parsed(skipped) %d(%d) counts in %s" % (entry_count, skip_count, page))
                    break
            
            if (
                current_tag.name == "h3"
                and current_tag.span
                and current_tag.span.get('class') == ["mw-headline"]
                and 'id' in current_tag.span.attrs
                and date_pattern.match(current_tag.span.get('id'))
            ):
                date_text = current_tag.span.get_text()
                try:
                    current_date = parse_date(date_text)
                except ValueError:
                    logger.error("Unable to parse date: %s" % str(current_tag))
                    logger.error("    page_id: %d" % page)
                    raise
            elif current_tag.name == "ul":
                if current_date > end_timestamp:
                    continue
                for item in current_tag.find_all('li'):
                    # Skip table of contents
                    c = item.get('class')
                    if c and 'toclevel-1' in c:
                        continue
                    # Parse the entry
                    try:
                        entry = get_entry(project_name, current_date, item, logger)
                    except ValueError:
                        logger.error("  Error parsing: %s" % item.get_text())
                        logger.error("    page_id: %d" % page)
                        raise
                    except AssertionError:
                        raise
                    except StopIteration:
                        # Probably testing code to skip
                        continue
                    except UnboundLocalError:
                        # Crawl stopped in the middle of multi-page entry
                        # Just skip to the first full entry
                        break
                    except:
                        logger.error("  Error parsing: %s" % item.get_text())
                        logger.error("    page_id: %d" % page)
                        raise
                    if entry[2] == 0:
                        logger.error("  get_entry() returned without action")
                        logger.error("    page_id: %d" % page)
                        raise AssertionError
                    k = (entry[1], entry[3], entry[2])
                    try:
                        prev = entries[k]
                        if prev != entry:
                            logger.error("  Contradictory entries:")
                            logger.error("    Keeping: " + str(prev))
                            logger.error("    Discarding: " + str(entry))
                        skip_count += 1
                    except KeyError:
                        entries[k] = entry
                        entry_count += 1
    logger.info("Parse complete")
    logger.info("Sortintg results")
    sorted_keys = sorted(entries.keys())
    logger.info("Writing results")
    quoted_name = urllib.quote(project_name.replace(" ", "_").encode('utf-8'), safe="")
    assessment_path = os.path.join(assessment_file % quoted_name)
    try:
        with open(assessment_path, "wb") as f:
            try:
                f.write((u"\t".join(columns) + u"\n").encode('utf-8'))
                for k in sorted_keys:
                    entry = entries[k]
                    row = u"\t".join([unicode(x) for x in entry]) + u"\n"
                    f.write(row.encode('utf-8'))
            except IOError:
                logger.error("Error writing: %s" % str(entry))
                raise ValueError
    except IOError:
        logger.error("Error opening: %s" % assessment_path)
        raise ValueError
    # Prevent running out of filehandlers if python procrastinates
    try:
        f.close()
    except:
        pass
    logger.info("Marking complete")
    with open(done_parse % clean_name, "wb") as f:
        f.write(project_name.encode('utf-8'))
    try:
        f.close()
    except:
        pass
    logger.info("Project %s complete" % project_name)
    handlers = logger.handlers[:]
    for handler in handlers:
        handler.close()
        logger.removeHandler(handler)
    
# Load project names, ignore duplicates
project_names = []
unique_names = set()
with open(project_tsv, "rb") as f:
    lines = enumerate(f.read().decode('utf-16-le').split(u"\n"))
    lines.next()
    for i, line in lines:
        if len(line) == 0:
            continue
        name, unique = line.split(u"\t")
        if unique not in unique_names:
            unique_names.add(unique) 
            project_names.append(name)
try:
    # Prevent running out of filehandlers if python procrastinates
    f.close()
except:
    pass

# Only run testing project (should usually be commented out)
if test_only:
    parse(test_project)
    sys.exit()

# Parse all projects
for project_name in sorted(project_names):
    clean_name = clean_name = project_name.replace("/", "_")
    # If the first arg is a project name, skip to that arg
    try:
        if sys.argv[1] > project_name:
            logger.info("Skipping from arg: %s" % project_name)
            continue
    except IndexError:
        pass
    try:
        if sys.argv[2] <= project_name:
            logger.info("Skipping from arg: %s" % project_name)
            break
    except IndexError:
        pass
    # Make sure project hasn't already been crawled
    try:
        os.stat(done_parse % clean_name)
        logger.info("Skipping complete: %s" % project_name)
        continue
    except OSError:
        pass
    logger.info("Beginning %s" % project_name)
    logger.info("  Decompressing cache")
    project_cache_tar = cache_tar % clean_name
    project_cache_dir = cache_dir % clean_name
    subprocess.call(["tar", "-xzf", project_cache_tar])
    logger.info("  Beginning parse")
    try:
        parse(project_name)
        logger.info("  Parsed successfully")
    except:
        logger.error(traceback.format_exc())
    logger.info("  Cleaning up")
    try:
       shutil.rmtree(project_cache_dir)
    except:
        # Will error if we were unable to successfully decompress
        pass

