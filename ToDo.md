1. ~~In the series feed we will keep the "Following" & "Ignored" categories, and add a new one called "Inbox"...~~ DONE — docs (Requirements FR-081–FR-085/AC-027–AC-031, Data-Contracts, Architecture-Overview, Constraints-Register C-010/F-006, Change-Log) and code (`models.py`, `tools/migrate_005_series_following.sh`, `dedup.py`, `main.py`, `routes.py`, `app.js`, `config.yaml.example`) both shipped and verified end-to-end against an isolated test DB + headless-browser screenshot. Migration NOT yet run against the real `config.yaml` MySQL database — run `tools/migrate_005_series_following.sh` before starting the app against production data.

2. In the series feed we will keep the "Not-Ignored" & "Ignore" categories, and add a new one called "Following". The user can select and assign the category (as we do with "Ignore"), and/or filter by name. The name filtering uses an specific entry in the "config.yaml" that has the string patterns to filter and add the "Following" flag/category. Additionally the flag/category can be assigned as we do now with the "Ignore". 
3. In the series feed we need different views: Only title or full. And there should be a filter so we can show only new series (if it is not in Season 1 Episode 1 maybe it was to a "Potentially ignore" category?

## This is useful for all categories
1. We now have "Mark as Read" button. Add same buttons with "all above" & "all below".

## Is this really a Bug??
1. "Ignore all" in series does not restrict to the present filter. For example, if "Unread" & "Not-Ignored", the "Ignore all" should only apply to the filtered entries.

----

BigChange

I want to first work on the documentation we have (use the sdlc skill if you need to). Make all the questions you need so we have a proper documentation. Once you wrap that up, save the documentation changes and pause and ask for confirmation to start working on the code changes.

SmallChange

Do the documentation and code changes at the same time. Ask me if you have questions.

----

I need you to fetch a design from a pre-existing application. Can you do that?

I have an existing web app in my local computer. It is a git repo and includes documentation of the project as well. It currently lacks the UI design documentation, and I want to have that in Pencil.
