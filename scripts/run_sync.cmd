@echo off
cd /d "%~dp0.."
python scripts\sync_listings.py >> data\sync.log 2>&1
if exist data\osm\mari_el.pbf python scripts\build_buildings.py >> data\sync.log 2>&1
