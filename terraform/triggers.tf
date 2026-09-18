resource "null_resource" "schema_tables_sql_trigger" {
  triggers = {
    file_hash = filesha1("${path.module}/schema-tables.sql")
  }

  provisioner "local-exec" {
    command = "echo Triggered re-upload of schema-tables.sql"
  }
}

resource "null_resource" "schema_data_sql_trigger" {
  triggers = {
    file_hash = filesha1("${path.module}/schema-data.sql")
  }

  provisioner "local-exec" {
    command = "echo Triggered re-upload of schema-data.sql"
  }
}

resource "null_resource" "csv_files_trigger" {
  triggers = {
    files_hash = sha1(join("", [
      # issue-513 STEP 3. This list is EXACTLY the files the seed Job loads
      # (`storage.tf` uploads these two and no others; `schema-data.sql` has
      # two matching LOAD DATA statements). It used to be
      # `fileset(".../csv", "**/*")`, which is wrong in two directions:
      #
      #   __pycache__/*.pyc  gitignored + machine-local, and `fileset` reads
      #                      the FILESYSTEM, not git -- so two engineers at the
      #                      same commit computed DIFFERENT hashes, and running
      #                      the generator locally re-fired the Job.
      #   generate_words_*.py  a build-time input. Editing it re-fired the Job
      #   HSK[1-6].csv         even though neither file is ever loaded.
      #
      # Verified empirically, not assumed: `terraform console` on this
      # directory expands the old glob to 10 entries including the .pyc.
      #
      # 🔴 Keep this an EXPLICIT LIST, not a glob. A glob silently re-widens
      # when a file is added to csv/; this list reds `test_seed_hash_inputs_513.py`
      # instead, which is the outcome you want -- that test derives the
      # expected set from storage.tf, so adding a THIRD loaded CSV correctly
      # demands a change here.
      filesha1("${path.module}/csv/wordsets.csv"),
      filesha1("${path.module}/csv/words.csv"),
    ]))
  }

  provisioner "local-exec" {
    command = "echo Triggered re-upload of CSV files"
  }
}