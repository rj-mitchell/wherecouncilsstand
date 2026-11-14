BEGIN TRANSACTION;
CREATE TABLE answer_cache (key TEXT PRIMARY KEY, at TEXT NOT NULL, events TEXT NOT NULL);
INSERT INTO "answer_cache" VALUES('six-days-old','2026-11-07T08:00:00+00:00','[{"type": "final", "answer": {"segments": [{"text": "No records found. The minutes contain no records matching this question and these filters.", "sources": [], "cited": [], "status": "connective"}], "markdown": "No records found.", "no_records": true, "citations_total": 0, "citations_invalid": 0, "grounded_ratio": 1.0, "unsupported_segments": 0}, "cached": true}]');
INSERT INTO "answer_cache" VALUES('an-hour-old','2026-11-13T11:00:00+00:00','[{"type": "plan", "plan": {"question": "Bins?"}}, {"type": "final", "answer": {"segments": [{"text": "Barnsley''s cabinet said the toilets were \"well used\".", "sources": [1], "cited": [{"source": 1, "cited_text": "the public toilets in the town centre are well used"}], "status": "cited", "loaded": [], "misquotes": []}, {"text": " In the debate that followed:", "sources": [], "cited": [], "status": "unsupported", "loaded": [], "misquotes": []}, {"text": " Guildford agreed to review opening hours.", "sources": [2], "cited": [{"source": 2, "cited_text": "RESOLVED that opening hours be reviewed"}], "status": "cited", "loaded": [], "misquotes": []}, {"text": " This was a turning point for every council in the county.", "sources": [], "cited": [], "status": "unsupported", "loaded": [{"start": 12, "end": 19, "word": "turning"}], "misquotes": []}], "markdown": "Barnsley''s cabinet said the toilets were \"well used\". In the debate that followed: Guildford agreed to review opening hours. This was a turning point for every council in the county.", "no_records": false, "citations_total": 2, "citations_invalid": 0, "grounded_ratio": 0.5, "unsupported_segments": 2, "loaded_words": 1, "quotes_total": 1, "quotes_unverified": 0}, "cached": true}]');
INSERT INTO "answer_cache" VALUES('long-expired','2026-10-01T00:00:00+00:00','[]');
CREATE TABLE briefings (
    id TEXT PRIMARY KEY, at TEXT NOT NULL, question TEXT NOT NULL, options TEXT NOT NULL, events TEXT NOT NULL,
    withdrawn_at TEXT, withdrawn_reason TEXT);
INSERT INTO "briefings" VALUES('abc123','2026-11-05T08:00:00+00:00','What has Barnsley decided about public toilets?','{"mode": "summary", "plan": null, "sources_only": false}','[{"type": "plan", "plan": {"question": "Bins?"}}, {"type": "text", "text": "Barnsley''s cabinet said the toilets were \"well used\". In the debate that followed: Guildford agreed to review opening hours. This was a turning point for every council in the county."}, {"type": "final", "answer": {"segments": [{"text": "Barnsley''s cabinet said the toilets were \"well used\".", "sources": [1], "cited": [{"source": 1, "cited_text": "the public toilets in the town centre are well used"}], "status": "cited", "loaded": [], "misquotes": []}, {"text": " In the debate that followed:", "sources": [], "cited": [], "status": "unsupported", "loaded": [], "misquotes": []}, {"text": " Guildford agreed to review opening hours.", "sources": [2], "cited": [{"source": 2, "cited_text": "RESOLVED that opening hours be reviewed"}], "status": "cited", "loaded": [], "misquotes": []}, {"text": " This was a turning point for every council in the county.", "sources": [], "cited": [], "status": "unsupported", "loaded": [{"start": 12, "end": 19, "word": "turning"}], "misquotes": []}], "markdown": "Barnsley''s cabinet said the toilets were \"well used\". In the debate that followed: Guildford agreed to review opening hours. This was a turning point for every council in the county.", "no_records": false, "citations_total": 2, "citations_invalid": 0, "grounded_ratio": 0.5, "unsupported_segments": 2, "loaded_words": 1, "quotes_total": 1, "quotes_unverified": 0}, "briefing_id": "abc123"}]',NULL,NULL);
INSERT INTO "briefings" VALUES('gone456','2026-11-05T08:01:00+00:00','Which council closed its toilets?','{"mode": "summary"}','[{"type": "final", "answer": null}]','2026-11-05T08:02:00+00:00','It misattributed a decision to the wrong council.');
INSERT INTO "briefings" VALUES('old789','2026-11-05T08:01:00+00:00','And libraries?','{"mode": "summary", "plan": null, "history": [{"question": "What have councils decided about bin collections?", "answer": "Barnsley kept them weekly."}], "sources_only": false}','[{"type": "final", "answer": null}]',NULL,NULL);
INSERT INTO "briefings" VALUES('bare000','2026-11-05T08:30:00+00:00','Withdrawn with nothing said?','{}','[]','2026-11-06T09:00:00+00:00','');
CREATE TABLE kv (key TEXT PRIMARY KEY, value TEXT);
INSERT INTO "kv" VALUES('visitor_salt:2026-11-13','5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a5a');
CREATE TABLE questions (day TEXT NOT NULL, visitor TEXT NOT NULL, n INTEGER NOT NULL,
    PRIMARY KEY (day, visitor));
INSERT INTO "questions" VALUES('2026-11-13','8477f5602fc12a9348d44ac7',2);
INSERT INTO "questions" VALUES('2026-11-13','7d08228e5fb8620beb0b2901',1);
CREATE TABLE reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, kind TEXT NOT NULL, page TEXT, message TEXT NOT NULL,
    contact TEXT, closed_at TEXT);
INSERT INTO "reports" VALUES(1,'2026-07-03T10:05:00+00:00','error',NULL,'From a row with nothing else in it',NULL,NULL);
INSERT INTO "reports" VALUES(2,'2026-11-07T08:00:00+00:00','error','/votes/E08000038:1:10:0','The vote is shown on the wrong side.','','2026-11-07T09:00:00+00:00');
INSERT INTO "reports" VALUES(3,'2026-11-07T08:00:00+00:00','takedown','/councils/E08000038','Please remove my name.','',NULL);
INSERT INTO "reports" VALUES(4,'2026-11-07T08:00:00+00:00','other','','Something else entirely','c@d.org',NULL);
INSERT INTO "reports" VALUES(5,'2026-11-07T08:00:00+00:00','unfair','','A loaded word.','','2026-11-07T09:00:00+00:00');
CREATE TABLE statements (
    id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, page TEXT NOT NULL, council TEXT, name TEXT NOT NULL,
    role TEXT NOT NULL, text TEXT NOT NULL, link TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending', shown_on TEXT, ended_at TEXT, reason TEXT, log TEXT NOT NULL DEFAULT '[]');
INSERT INTO "statements" VALUES(1,'2026-07-01T09:00:00+00:00','/councils/E08000038','E08000038','X  Y','Z W','Vote for me.','','','declined',NULL,'2026-07-02T09:00:00+00:00','It appeals for votes.','[{"at": "2026-07-01T09:00:00+00:00", "action": "received"}, {"at": "2026-07-02T09:00:00+00:00", "action": "declined", "note": "It appeals for votes."}]');
INSERT INTO "statements" VALUES(2,'2026-07-01T09:00:00+00:00','/votes/E08000038:1:10:0','E08000038','Steve Houghton','Councillor, Barnsley Metropolitan Borough Council','I voted against this motion because the council had already agreed a review of collections, and the minutes of that meeting set it out.','https://example.org/r?a=1&b=2','','withdrawn','2026-07-02','2026-07-03T09:00:00+00:00','Withdrawn by its author.','[{"at": "2026-07-01T09:00:00+00:00", "action": "received"}, {"at": "2026-07-02T09:00:00+00:00", "action": "published", "note": "Phoned the members'' room, 2 July."}, {"at": "2026-07-03T09:00:00+00:00", "action": "withdrawn", "note": "Withdrawn by its author."}]');
INSERT INTO "statements" VALUES(3,'2026-08-12T09:00:00+00:00','/councils/E07000209','E07000209','Tim Anderson','Councillor','Withdrawn in August.','','tim@guildford.gov.uk','withdrawn','2026-08-12','2026-08-13T11:00:00+00:00','Withdrawn by its author.','[{"at": "2026-08-12T09:00:00+00:00", "action": "received"}, {"at": "2026-08-12T09:00:00+00:00", "action": "published", "note": "Reply from tim@guildford.gov.uk, 12 August."}, {"at": "2026-08-13T11:00:00+00:00", "action": "withdrawn", "note": "Withdrawn by its author."}]');
INSERT INTO "statements" VALUES(4,'2026-11-07T09:00:00+00:00','/votes/E08000038:1:10:0','E08000038','Steve Houghton','Councillor, Barnsley Metropolitan Borough Council','My newer words, as I sent them.','https://barnsley.moderngov.co.uk/ieListDocuments.aspx?MId=1','cllr@barnsley.gov.uk','published','2026-11-11',NULL,NULL,'[{"at": "2026-11-07T09:00:00+00:00", "action": "received"}, {"at": "2026-11-10T10:00:00+00:00", "action": "published", "note": "Reply from the address on the council''s website, 12 November."}, {"at": "2026-11-11T15:00:00+00:00", "action": "updated", "note": "shown_on, text"}]');
INSERT INTO "statements" VALUES(5,'2026-11-07T09:00:00+00:00','/b/abc123','E08000038','Barnsley Council','Democratic services','Our view.','','dem@barnsley.gov.uk','published','2026-11-10',NULL,NULL,'[{"at": "2026-11-07T09:00:00+00:00", "action": "received"}, {"at": "2026-11-10T10:00:00+00:00", "action": "published", "note": "Reply from democratic services."}]');
INSERT INTO "statements" VALUES(6,'2026-11-07T09:00:00+00:00','/councils/E07000209','E07000209','Julia McShane','Leader, Guildford Borough Council','First para.

Second.','','leader@guildford.gov.uk','pending',NULL,NULL,NULL,'[{"at": "2026-11-07T09:00:00+00:00", "action": "received"}, {"at": "2026-11-10T10:00:00+00:00", "action": "updated", "note": "role"}]');
INSERT INTO "statements" VALUES(7,'2026-11-07T09:00:00+00:00','/councils/E08000038','E08000038','Recent Author','Councillor','Shown for a day only.','','recent@barnsley.gov.uk','withdrawn','2026-11-10','2026-11-11T15:00:00+00:00','Withdrawn by its author.','[{"at": "2026-11-07T09:00:00+00:00", "action": "received"}, {"at": "2026-11-10T10:00:00+00:00", "action": "published", "note": "Letter."}, {"at": "2026-11-11T15:00:00+00:00", "action": "withdrawn", "note": "Withdrawn by its author."}]');
CREATE TABLE usage (
    at TEXT NOT NULL, day TEXT NOT NULL, visitor TEXT, kind TEXT NOT NULL, model TEXT,
    input_tokens INTEGER, output_tokens INTEGER, cache_read_tokens INTEGER, cache_write_tokens INTEGER,
    cost_usd REAL NOT NULL);
INSERT INTO "usage" VALUES('2026-07-01T09:00:00+00:00','2026-07-01','0123456789abcdef01234567','parse','claude-haiku-5-5',1000,200,0,0,0.0002);
INSERT INTO "usage" VALUES('2026-07-01T09:00:00+00:00','2026-07-01','0123456789abcdef01234567','answer','claude-sonnet-5-5',9000,700,3000,2000,0.0266);
INSERT INTO "usage" VALUES('2026-07-03T10:00:00+00:00','2026-07-03',NULL,'parse',NULL,NULL,NULL,NULL,NULL,0.0004);
INSERT INTO "usage" VALUES('2026-10-31T23:30:00+00:00','2026-10-31','89abcdef0123456789abcdef','answer','claude-sonnet-5-5',31000,1900,0,3600,0.0828);
INSERT INTO "usage" VALUES('2026-11-01T00:00:10+00:00','2026-11-01','fedcba9876543210fedcba98','answer','claude-sonnet-5-5',9000,700,3000,2000,0.0266);
INSERT INTO "usage" VALUES('2026-11-13T07:00:00+00:00','2026-11-13','8477f5602fc12a9348d44ac7','parse','claude-haiku-5-5',1000,200,0,0,0.0002);
INSERT INTO "usage" VALUES('2026-11-13T07:00:00+00:00','2026-11-13','8477f5602fc12a9348d44ac7','answer','claude-sonnet-5-5',9000,700,3000,2000,0.0266);
INSERT INTO "usage" VALUES('2026-11-13T07:10:00+00:00','2026-11-13','8477f5602fc12a9348d44ac7','parse','claude-haiku-5-5',1000,200,0,0,0.0002);
INSERT INTO "usage" VALUES('2026-11-13T07:10:00+00:00','2026-11-13','8477f5602fc12a9348d44ac7','answer','claude-sonnet-5-5',105123,2431,3712,0,0.235298);
INSERT INTO "usage" VALUES('2026-11-13T07:10:00+00:00','2026-11-13','7d08228e5fb8620beb0b2901','parse','claude-haiku-5-5',1000,200,0,0,0.0002);
INSERT INTO "usage" VALUES('2026-11-13T07:10:00+00:00','2026-11-13','7d08228e5fb8620beb0b2901','answer','claude-sonnet-5-5',31000,1900,0,3600,0.0828);
INSERT INTO "usage" VALUES('2026-11-13T07:10:00+00:00','2026-11-13','7d08228e5fb8620beb0b2901','parse','claude-haiku-5-5',1000,200,0,0,0.0002);
CREATE INDEX usage_day ON usage (day);
CREATE INDEX statements_page ON statements (status, page);
DELETE FROM "sqlite_sequence";
INSERT INTO "sqlite_sequence" VALUES('statements',7);
INSERT INTO "sqlite_sequence" VALUES('reports',5);
COMMIT;
