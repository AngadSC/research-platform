"""A full-size fake lab for testing the app the way a real lab would use it: a PI, admins,
postdocs, students, research assistants and outside viewers, spread over nine projects in every
status. `people.build()` makes the people and projects; each other module adds one area through
the service layer and exposes `seed(ctx)`. Everything is obviously fake (FAKE, example.test,
.invalid hosts). Run with `manage.py seed_full_lab`."""
