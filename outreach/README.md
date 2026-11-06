# Letters to councils

Requests for permission to read councils' meetings sites, where robots.txt forbids it or the site refuses the
crawler (docs/DECISIONS.md, 2: asked, not worked around). `scripts/outreach.py` writes them from the registry and the
addresses each council publishes; they are kept here as the record of who was asked, and when.

Each starts with its To: and Subject: lines, and is sent from the charity's Gmail account by Where MPs Stand's
`deploy/mail.sh` (its `docs/HOSTING.md`, "Email from the server"), so the links arrive as written:

    bash /opt/hansardgpt/deploy/mail.sh send /opt/wherecouncilsstand/outreach/2026-11/*.txt

A letter already sent is skipped, so the command is safe to repeat. Replies arrive in the account's inbox.

The server's address is never committed: the repository is public, and Cloudflare keeps the server's address
hidden. A letter to a council whose site refuses or doesn't answer the server says `[the server's IP address, as
given in the letter sent]` instead (the script writes it so, and `tests/test_outreach.py` fails if an address is
committed), and the address is filled in only when sending. Those letters are sent one at a time, not with the
command above: copy the letter outside the repository, keeping its file name (the record of letters already sent
goes by it), put the address in the copy, send the copy, and delete it. For example:

    cp /opt/wherecouncilsstand/outreach/2026-11/camden.txt /root/
    nano /root/camden.txt
    bash /opt/hansardgpt/deploy/mail.sh send /root/camden.txt && rm /root/camden.txt

Send them before running the command above, which would otherwise send them with the placeholder; once sent,
they are skipped. For the letter for post, put the address in before printing it.

A council that agrees by adding "User-agent: WhereCouncilsStand / Allow: /" to its robots.txt is read at the next
load (`sources/robots.py` checks rules under that name). One that agrees by email, leaving robots.txt as it is,
needs its permission recorded in the registry before it is read.

Councils that publish no email address get a letter for post instead, in the batch's `post/` folder (the send
command above doesn't take it). Print it, sign it and post it; it asks for a reply by email.

## The robots.txt batch (`2026-11-robots/`)

Drafted on 6 November 2026, not sent. When the Modern.gov reader began to check robots.txt (decision 21), 44 sites
were found to forbid reading, most of which the site had already read. Each letter says so plainly, apologises, and
asks for permission; one letter goes to a site two bodies share (South Hams and West Devon; East Sussex, with the
Sussex and Brighton Combined County Authority). Eastleigh, Richmond upon Thames and Wandsworth were already written
to in the first batch, because their sites refused the server, so they aren't written to again.

Before sending:

1. **Find each address.** The To: line says `[the council's democratic services address, to be found before
   sending]`: put in the address each council publishes for its democratic services team, as for the first batch.
   (Their meetings sites can't be read for it: that is the point of the letter.)
2. **Put in the server's address.** Every letter in this batch gives it, so the whole batch is filled in a copy outside
   the repository, keeping the file names, then sent and deleted:

       cp -r /opt/wherecouncilsstand/outreach/2026-11-robots /root/robots-letters
       sed -i 's/\[the server'"'"'s IP address, as given in the letter sent\]/<the address>/' /root/robots-letters/*.txt
       grep -L "^To: .*@" /root/robots-letters/*.txt        # any letter still without an address
       bash /opt/hansardgpt/deploy/mail.sh send /root/robots-letters/*.txt && rm -r /root/robots-letters

A council that agrees has its `modgov_status` set back to `ok` in `data_static/councils.csv`: its withheld record
returns, and the next update reads it again (docs/DATA.md, "Robots.txt").
