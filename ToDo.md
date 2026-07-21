## ToDo

1. In News, each day should have a "Mark as Read" button which only applies to that day. The name will be different, "Mark day as Read".
2. Add for the News feed a text tag that will be used to group them in tabs. So News will have a list of tag as tabs which each contain a number of feeds. All configured in "config.yml". Each entry will have "name", "url", "type" & the new property "tag".

## ToDo later

1. Need to consume a different kind of "feed". It is the listing of a webpage which has links to articles with the title and a description. It will be a new kind of feed like "News", but it won't use RSS as source. Just and HTML listing. It will require configuration for each feed to figure out the HTML structure and mapping into a feed like record. For this new feed use `https://betovaldez.com.ar/category/actualidad/` which should match with `http://betovaldez.com.ar/feed/` to model it.
2. There needs to be a new category which can save links in all types of feeds. Feeds can be marked as "ToKeep"
3. There should be a housekeeping process that deletes old links to keep DB size under control

## For later

1. We now have "Mark as Read" button. Add same buttons with "all above" & "all below".
2. The export functionality in the News type feed should apply to the current view (not only for unread as it do now).
3. For all feeds there should be a new view that's all (read & unread) and which is order by date of ingestion and it shows unread items before read items.

----

General

When coding, generate a plan and ask for all permissions at once. And also ask for general tool access, not particular commands.
Ask for general tool access, not particular commands. If necessary, create a plan and ask for all permissions at once.

BigChange

I want to first work on the documentation we have (use the sdlc skill if you need to). Make all the questions you need so we have a proper documentation. Once you wrap that up, save the documentation changes and pause and ask for confirmation to start working on the code changes.

SmallChange

Do the documentation and code changes at the same time. Ask me if you have questions.

----

I need you to fetch a design from a pre-existing application. Can you do that?

I have an existing web app in my local computer. It is a git repo and includes documentation of the project as well. It currently lacks the UI design documentation, and I want to have that in Pencil.
