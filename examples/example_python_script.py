from snowflake_connection import *

"""
FIRST-TIME SETUP
================

1. Clone the repository:

    git clone https://github.com/arc-sandbox/<org-url>
    cd arc-sandboxes

2. Create and activate a virtual environment:

    Windows:
        python -m venv .venv
        .venv\Scripts\activate

3. Install the repository in editable mode:

    pip install -e .

    This makes the local `snowflake_connection` package available
    to Python and automatically picks up future code changes.

4. Verify the installation:

    python -c "from snowflake_connection import run_query; print('Import successful')"

5. Ensure you have access to Snowflake and that your email address is added to the run_query() function call below.

6. Insert your email address into the variable `email_address` below.

7. Run this script:

    python examples/example_python_script.py

Troubleshooting
---------------

If you receive:

    ModuleNotFoundError: No module named 'snowflake_connection'

ensure:
    - You are running inside the project's virtual environment.
    - `pip install -e .` completed successfully.
    - You are running the script from the repository root.


"""

email_address = 'your_email_address'

df_metric = run_query("SELECT * FROM DATA_EXCHANGE_LAYER.METRIC LIMIT 10", email_address = email_address)

print('Transition Arc Metrics Sample:')
print(df_metric)

df_submetric = run_query("SELECT * FROM DATA_EXCHANGE_LAYER.SUBMETRIC LIMIT 10", email_address = email_address)

print('Transition Arc Submetrics Sample:')
print(df_submetric)

close_connection()