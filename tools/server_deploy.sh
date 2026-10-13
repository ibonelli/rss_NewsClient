# source venv/bin/activate
# tools/migrate_008_saved_entries.sh
sudo git pull
sudo chown www-data:www-data -R *
sudo chown ignacio:ignacio -R logs
sudo systemctl restart pelis-feed-web
