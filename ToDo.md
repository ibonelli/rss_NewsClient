## ToDo

1. Need to find a way to import marked as "to follow" from previous system, and need to find a way to do the same in the new system. Could be a different system that runs on a separate cron. So we create a list of links to the articles, and then the other system goes to process them. Or just collect them and I can pull the list to use in a different system.

## For later

1. There should be a housekeeping process that deletes old links to keep DB size under control.
2. Need to consume a different kind of "feed". It is the listing of a webpage which has links to articles with the title and a description. It will be a new kind of feed like "News", but it won't use RSS as source. Just and HTML listing. It will require configuration for each feed to figure out the HTML structure and mapping into a feed like record. For this new feed use `https://betovaldez.com.ar/category/actualidad/` which should match with `http://betovaldez.com.ar/feed/` to model it.

----

General

When coding, generate a plan and ask for all permissions at once. Generate a list of commands you'll run, and request and ask for all permissions at once.

BigChange

I want to first work on the documentation we have (use the sdlc skill if you need to). Make all the questions you need so we have a proper documentation. Once you wrap that up, save the documentation changes and pause and ask for confirmation to start working on the code changes.

SmallChange

Do the documentation and code changes at the same time. Ask me if you have questions.

----

I need you to fetch a design from a pre-existing application. Can you do that?

I have an existing web app in my local computer. It is a git repo and includes documentation of the project as well. It currently lacks the UI design documentation, and I want to have that in Pencil.
