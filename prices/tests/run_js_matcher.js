// stdin: JSON list of titles -> stdout: JSON list of match results (used by test_matcher.py)
const fs = require('fs'), path = require('path');
const { makeMatcher } = require('../matcher.js');
const D = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'data', 'matcher.json'), 'utf8'));
const m = makeMatcher(D);
const titles = JSON.parse(fs.readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(titles.map(t => m.match(t))));
