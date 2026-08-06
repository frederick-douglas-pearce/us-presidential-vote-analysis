---
layout: post
title: "Presidential Elections Are Messy. The Data Has to Carry the Story."
date: 2026-08-03 00:00:00-0800
description: "The hard part isn't the numbers — it's recording why a number isn't there."
categories: ["american-history"]
tags: ["electoral-college", "american-history", "data-quality", "us-presidential-vote-analysis"]
og_image: https://frederick-douglas-pearce.github.io/assets/img/presidential-elections-are-messy-og.png
og_card_source: social/images/2026-08-03-linkedin-presidential-elections-are-messy/og-card.png
featured: false
---

In 1864, eleven states took no part in the [presidential election](https://www.archives.gov/electoral-college/1864). Not "had bad turnout." Took no part. The country was in the midst of the Civil War, and those states had seceded.

The National Archives, the official record for electoral votes, lists all thirty-six states of that year, and a note beside the table explains it in plain language: *"The Confederate States did not participate in the election of 1864 because they seceded from the Union."* Nothing is hidden. But inside the table, those eleven states carry a dash in every electoral-vote column. A dash is also what that same table prints for a candidate who won no electoral votes in a state where the election was held normally. One mark, two entirely different facts: *this candidate lost here*, and *there was no election here*.

The American Presidency Project at the University of California, Santa Barbara (UCSB), the most complete popular-vote compilation reaching back this far, does the opposite. Its [1864 page](https://www.presidency.ucsb.edu/statistics/elections/1864) lists twenty-five states, and the other eleven are simply not on it — no row, no dash, no asterisk. The only trace is one sentence of prose: *"Eleven Confederate states did not participate in the election because of the Civil War."*

Neither of those is a mistake. Both are sensible editorial choices for a document a person reads, and in both the sentence that resolves the ambiguity is sitting right there next to the table. But for a program reading either page, the prose may as well not exist. In one record the dash becomes a number, the number is zero, and zero is a claim about what happened. In the other, eleven states quietly cease to exist for a year, and nothing in the shape of the data says otherwise.

Translating a document written to be read into a structure built to be computed on is the hard part.

## What this is actually for

This series documents a project that assembles roughly two centuries of presidential elections into a single queryable record: electoral votes from the National Archives, popular votes from separate sources that don't cover the same years or spell the same names the same way. Two goals sit behind it.

The first is to faithfully reconstruct the calculus that selected each president, including the years it went sideways. The familiar story is that one candidate wins a majority of the appointed electoral votes. Several elections didn't work that way.

The second is harder: to ask *what-if* questions against historically accurate vote counts. What would a different rule have produced in 1876? In 2000? That's the interesting question, and the one with a trapdoor under it, because a what-if is only as honest as the numbers it runs on. The fastest way to get a confidently wrong answer about a nineteenth-century election is to feed it a zero that was never a real zero.

So the recurring problem here isn't recording numbers. Most numbers are easy. It's recording **why a number isn't there**, and doing it in a way that survives being merged with a second record and aggregated by someone else.

## One empty cell, five different histories

Collapse the voting record into a single count column and at least five different facts about American history flatten into the same cell.

**It was actually zero.** An election was held, a candidate ran, and they won no electoral votes in that state. Roughly 59 percent of the candidate-by-state electoral-vote figures parsed to date are zeros, and most mean exactly this. It's the majority case by a wide margin, and it's load-bearing. Zero isn't automatically a concern. It's just not the only thing an empty-looking cell can mean.

**The candidate wasn't on the ballot in that state.** Nineteenth-century ballot access was a state-by-state affair, and a national candidate could be entirely absent from a state's ballot. "On the ballot and got nothing" and "never on the ballot" are different claims, and only one of them is a zero.

**The state's legislature chose the electors, so no popular vote was ever held.** The Constitution has no objection: states appoint electors "in such manner as the legislature may direct," and it promises no one a ballot. South Carolina did it this way in every election through 1860, which reads like a founding-era habit the country simply outgrew. Not quite. The last legislature to pick presidential electors with no popular vote at all was **Colorado's, in 1876**, a state admitted too close to the election to organize one.

**The state took no part in the election.** This is 1864's eleven, and it's distinct from the case above: South Carolina's electors in 1860 *existed*, and were legislature-chosen. Virginia's in 1864 did not exist at all.

**The election happened, but a source doesn't have the number.** A gap in what a source collected is a fact about the source, not about the election. Treating those gaps as zeros quietly merges two different histories: a place where nothing happened, and a place where something happened that this particular record doesn't carry.

These aren't five versions of the same kind of statement. The first two are facts about **a candidate in a place**. The next two are facts about **a place**, true of every candidate in it. The last is a fact about **the source's record itself**.

So the record has to store more than the number. It has to keep hold of which kind of statement each cell is making, and no single column can carry all three.

## How the record keeps them apart

The Archives table makes one design choice that carries most of the weight: it records **two** numbers, not one. Each state's allotment of electoral votes is kept separate from each candidate's take of them. So Virginia in 1864 has an allotment of zero, which alone is enough to recover "no electors were appointed here," because a participating state always has some. With a single "votes for this candidate" column, Virginia's zero and an Ohio loser's zero would be indistinguishable.

The second number also covers a UCSB blind spot. For 1864, UCSB lists twenty-five states. The Archives lists thirty-six, and exactly eleven have an allotment of zero: precisely the ones missing from the UCSB page. An absence carrying no markup at all in one source is recoverable and checkable from the other, so the eleven get written down deliberately rather than inferred from a hole. Neither record could do that alone.

The two numbers can't carry everything, and South Carolina shows why. In 1860, it has eight electoral votes and a perfectly ordinary row. Nothing in the Archives record hints that no popular vote was held there, and nothing should: electoral votes are what that source records.

So the status of each state in each year gets a structure of its own: one row for **every state in every election year**, not just the unusual ones. Complete rather than exceptions-only, because a list of exceptions can't distinguish "we checked and found nothing unusual" from "we never checked." Each row carries one of three values — a popular vote was held, the legislature chose the electors, or the state took no part — plus a free-text reason in the source's own words.

There is deliberately **no fourth value for "unknown"**. The database itself refuses one. An "unknown" bucket is where an unresolved gap goes to sit quietly forever. Without one, every gap has to be named, or the data doesn't load.

A check runs on every load, in both directions. A state marked as having held no popular vote must have **exactly zero** vote rows, and one marked as having held a popular vote must have **at least one**. That catches a failure no total can see. A state that disappears between reading a source and storing it takes its votes with it, and every total still reconciles, because the total went missing too.

The same principle turns up once more, in the electors themselves, the people who ultimately make the choice. In [2000](https://www.archives.gov/electoral-college/2000), one of the District of Columbia's three electors, Barbara Lett-Simmons, turned in a blank ballot: a deliberate protest at DC having no voting representation in Congress. It changed no outcome, but it does mean the national figures that year were **537 votes cast against 538 electors appointed**, and both numbers stay on the record.

That isn't bookkeeping fussiness. The threshold for winning is defined on the appointed number. The Twelfth Amendment requires a majority "of the whole number of Electors appointed," so collapsing the two quietly moves the bar that decides presidencies. Two numbers, kept apart, because they answer different questions.

## Where the two records meet

All of that care buys something specific. It's what lets us merge two independent records of the same elections without silently breaking the comparison.

Merging is exactly where a missing row and a zero row stop being distinguishable, because a merge only asks whether a match exists. It never asks what a non-match *means*. A row can be missing because the candidate lost, or because the source never covered that state. To a merge, both look the same: no match.

Which is why it matters that the electoral-vote record is complete rather than selective. The Archives prints a dash for every candidate in every state, and that dash parses into an explicit zero. A losing candidate still gets a row, carrying that zero, in every state they lost. Nobody is ever simply absent because they didn't win. That single property is what makes a question like *"who lost the Electoral College but won the popular vote"* answerable at all. The losers are still there to be counted, with their real electoral totals, when the two records are merged.

Had the record gone the other way, a merge over a selective record would have dropped precisely the rows the comparison exists to find. The totals would still have added up cleanly, because the missing rows were never there to be missed. A failure like that raises no error.

[This project](https://github.com/frederick-douglas-pearce/us-presidential-vote-analysis) made a version of that mistake once, briefly. The first build of the merge was written defensively, on the untested assumption that a losing candidate might not appear as a row for a state they lost. It was built to tolerate an absence that, it turned out, never occurs. The cost isn't the dead code. It's what that path would have done had the assumption ever been right: continue quietly past exactly the rows the analysis depends on. What caught it was checking the record's actual shape instead of guessing at it — every year, every state, verified before anything was built on top of it.

The merged result is [public](https://api.us-presidential-election-center.org) for the years both records cover (1976 through 2024), when a popular vote was held everywhere and none of this is in doubt. The pre-1976 years and the status record aren't in that public surface yet, for an unglamorous reason: some of the text explaining those absences comes from UCSB, which grants no republication rights, so it can be used for analysis but not for distribution.

## 1824, and which states belong in the denominator

Any comparison of a candidate's electoral-vote share to their popular-vote share has to decide which states count in the denominator. The reasonable-looking move is to count only the states that actually held a popular vote, and leave the legislature-chosen ones out, since they have no popular-vote number to contribute.

Apply that to [1824](https://www.archives.gov/electoral-college/1824). Six states — Delaware, Georgia, Louisiana, New York, South Carolina, and Vermont — had their electors chosen by legislature. Drop them, keep Andrew Jackson's 99 electoral votes, and Jackson has 99 of 190: **52 percent, a clear majority, elected outright**.

That is not what happened. Jackson had 99 of 261 electoral votes: **37.9 percent, a majority of nothing**. Under the Twelfth Amendment, the election went to the House of Representatives, which chose John Quincy Adams instead.

Treating *"this state held no popular vote"* as *"this state doesn't count"* is the missing-as-zero mistake wearing a different hat, and here it manufactures a constitutional majority that never existed. The fix is simple: every state that appointed electors belongs in the electoral-vote denominator, whether or not it held a popular vote.

The historical facts aren't at risk here. Adams became president in 1825, and no arithmetic changes it. A bad denominator silently corrupts *our own computed number* about 1824: 52 percent, no error, every appearance of a normal result. Anything built on top of it inherits the error. The 37.9 percent holds up only because those six states are recorded as *having held no popular vote*, a different thing entirely from having no data.

## Back to the eleven

It's easy to read all of this and still miss the eleven states from 1864, because nothing in either table tells you to go looking. The dashes parse cleanly. The twenty-five states that are there line up. Every total balances.

Eleven rows in this record now say *took no part*, each carrying its reason, and they say it only because someone read a sentence of prose beside a table and went to find out what it was doing there. Neither table asked for that, and neither could: a table has no way to tell you which of five things its blank-looking cell means.

None of this is unique to electoral history. Anyone building on a record they didn't compile runs into the same thing. Whoever did compile it made decisions about what to leave out, and those decisions are almost always explained somewhere that isn't the data: a codebook, a footnote, a sentence beside a table. The numbers arrive without them.

That's the actual challenge, and it's larger than it looks. Numbers survive any format they're put in. The reasons behind the numbers that aren't there survive only if the structure is built to hold them.

---

_Drafted with Claude Code. The ideas, claims, and any errors are mine._
