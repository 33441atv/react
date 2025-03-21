import streamlit as st
import pandas as pd
import base64
from io import StringIO
import datetime

st.set_page_config(page_title="Elementary School Overload Pay Calculator", layout="wide")

# Set up the header
st.title("Elementary School Overload Pay Calculator")
st.write("Upload a class roster CSV file to calculate teacher overload pay based on class sizes.")

# Create the sidebar for inputs
with st.sidebar:
    st.header("Settings")
    school_name = st.text_input("School Name (Optional)", "")
    number_of_weeks = st.number_input("Number of Weeks", min_value=1, max_value=5, value=4, 
                                     help="Number of school weeks in this month")
    pay_rate = st.number_input("Pay Rate ($)", min_value=0.01, value=1.25, step=0.01, format="%.2f",
                              help="Standard rate is $1.25 per student")
    
    st.markdown("---")
    st.subheader("File Upload")
    uploaded_file = st.file_uploader("Upload CSV File", type=["csv"], 
                                   help="File must include columns for Course Title, Staff Name, and Total Students")

# Define the data processing function
def process_data(df):
    try:
        # Ensure the required columns exist
        required_columns = ["Course Title", "Staff Name", "Total Students"]
        for col in required_columns:
            if col not in df.columns:
                st.error(f"The CSV file is missing required column: {col}")
                return None
        
        # Convert column types - make sure all numeric columns are properly converted
        for col in ["Total Students", "Max Students"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Fill NA values that might have resulted from conversion
        if "Total Students" in df.columns:
            df["Total Students"] = df["Total Students"].fillna(0)
        
        # Filter for required courses and students > 0
        df = df.dropna(subset=["Course Title", "Total Students"])
        
        # Filter for relevant courses
        def is_relevant_course(title):
            if not isinstance(title, str):
                return False
            title = title.upper()
            # First check if the title contains any of the keywords
            if not ("MUSIC" in title or "PHYS ED" in title or "ART" in title or "CREATIVE" in title):
                return False
            # Then check if there are students > 0, being careful about types
            try:
                students = df.loc[df["Course Title"] == title, "Total Students"].iloc[0]
                return pd.to_numeric(students, errors='coerce') > 0
            except (IndexError, TypeError):
                return False
        
        relevant_courses = df[df["Course Title"].apply(is_relevant_course)].copy()
        
        if relevant_courses.empty:
            st.warning("No relevant courses found (MUSIC, PHYS ED, ART, CREATIVE with students > 0)")
            return None
            
        # Determine base students based on course title
        def get_base_students(title):
            if not isinstance(title, str):
                return 23
            title = title.upper()
            if "MIXED" in title or " 1" in title or " 2" in title or " 3" in title:
                return 23
            elif " 4" in title or " 5" in title:
                return 26
            elif "KINDER" in title or " K" in title:
                return 22
            else:
                return 23  # default
                
        relevant_courses["Base Students"] = relevant_courses["Course Title"].apply(get_base_students)
        
        # Calculate overload - ensure we're working with numeric values
        relevant_courses["Total Students"] = pd.to_numeric(relevant_courses["Total Students"], errors='coerce').fillna(0)
        relevant_courses["Base Students"] = pd.to_numeric(relevant_courses["Base Students"], errors='coerce').fillna(0)
        relevant_courses["Total Overload"] = (relevant_courses["Total Students"] - 
                                             relevant_courses["Base Students"]).clip(lower=0).astype(int)
        
        # Calculate overload pay
        relevant_courses["Overload Pay"] = (relevant_courses["Total Overload"] * 
                                           pay_rate * number_of_weeks).round(2)
        
        # Sort by Staff Name
        relevant_courses = relevant_courses.sort_values("Staff Name")
        
        # Calculate totals by staff member
        staff_totals = relevant_courses.groupby("Staff Name").agg(
            {"Total Overload": "sum", "Overload Pay": "sum"}
        ).reset_index()
        
        # Calculate grand total
        grand_total = {
            "totalOverload": staff_totals["Total Overload"].sum(),
            "overloadPay": staff_totals["Overload Pay"].sum()
        }
        
        # Create a list to hold the final dataframe rows
        final_data = []
        
        # Add the detailed data with summary rows
        for staff_name, group in relevant_courses.groupby("Staff Name"):
            # Add all the courses for this staff member
            final_data.extend(group.to_dict('records'))
            
            # Add a summary row for this staff member
            summary = staff_totals[staff_totals["Staff Name"] == staff_name].iloc[0]
            summary_row = {
                "Year": "",
                "Organization": "",
                "Course Title": "TOTAL",
                "Staff Name": staff_name,
                "Total Students": "",
                "Base Students": "",
                "Total Overload": summary["Total Overload"],
                "Overload Pay": summary["Overload Pay"],
                "isSummary": True
            }
            final_data.append(summary_row)
            
            # Add a blank row
            blank_row = {col: "" for col in group.columns}
            blank_row["isBlank"] = True
            final_data.append(blank_row)
        
        # Convert the list back to a dataframe
        final_df = pd.DataFrame(final_data)
        
        # Create a filtered version with only non-zero overload
        if "isBlank" not in final_df.columns:
            final_df["isBlank"] = False
        if "isSummary" not in final_df.columns:
            final_df["isSummary"] = False
            
        non_zero_df = final_df[
            (final_df["isBlank"] == True) | 
            (final_df["isSummary"] == True) | 
            (final_df["Total Overload"] > 0)
        ].copy()
        
        # Get school name from Organization field if possible and not already set
        if not school_name and "Organization" in relevant_courses.columns:
            org = relevant_courses["Organization"].iloc[0]
            if isinstance(org, str) and "-" in org:
                suggested_name = org.split("-")[0].strip()
                st.sidebar.info(f"Detected school name: '{suggested_name}'")
        
        return {
            "data": final_df,
            "staff_totals": staff_totals,
            "grand_total": grand_total,
            "non_zero_data": non_zero_df
        }
        
    except Exception as e:
        st.error(f"An error occurred while processing the data: {str(e)}")
        return None

# Process data when file is uploaded
results = None
if uploaded_file is not None:
    try:
        df = pd.read_csv(uploaded_file)
        results = process_data(df)
    except Exception as e:
        st.error(f"Error reading the CSV file: {str(e)}")

# Display results if processing was successful
if results:
    # Create tabs for viewing different data
    tab1, tab2, tab3 = st.tabs(["All Courses", "Overload Courses Only", "Summary"])
    
    with tab1:
        st.subheader(f"{school_name or 'School'} Overload Pay Report - All Courses")
        st.write(f"Calculation Period: {number_of_weeks} week{'s' if number_of_weeks != 1 else ''} at ${pay_rate:.2f} per overload student")
        
        # Apply conditional formatting
        def highlight_rows(row):
            if row.get("isSummary") == True:
                return ['background-color: #e6f2ff'] * len(row)
            elif row.get("Total Overload", 0) > 0 and row.get("isSummary") != True:
                return ['background-color: #ffe6f2'] * len(row)
            return [''] * len(row)
        
        # Display detailed table
        display_cols = ['Year', 'Organization', 'Course Title', 'Staff Name', 
                        'Total Students', 'Base Students', 'Total Overload', 'Overload Pay']
        
        st.dataframe(results["data"][display_cols].style.apply(highlight_rows, axis=1))
    
    with tab2:
        st.subheader(f"{school_name or 'School'} Overload Pay Report - Overload Courses Only")
        st.write(f"Calculation Period: {number_of_weeks} week{'s' if number_of_weeks != 1 else ''} at ${pay_rate:.2f} per overload student")
        
        # Display only non-zero overload courses
        st.dataframe(results["non_zero_data"][display_cols].style.apply(highlight_rows, axis=1))
    
    with tab3:
        st.subheader("Summary of Teacher Overload Pay")
        
        # Display summary table
        summary_df = results["staff_totals"].copy()
        summary_df["Overload Pay"] = summary_df["Overload Pay"].round(2)
        
        # Add total row
        total_row = pd.DataFrame({
            "Staff Name": ["TOTAL"],
            "Total Overload": [results["grand_total"]["totalOverload"]],
            "Overload Pay": [results["grand_total"]["overloadPay"]]
        })
        summary_display = pd.concat([summary_df, total_row])
        
        def highlight_summary(row):
            if row["Staff Name"] == "TOTAL":
                return ['background-color: #e6f2ff; font-weight: bold'] * len(row)
            elif row["Total Overload"] > 0:
                return ['background-color: #ffe6f2'] * len(row)
            return [''] * len(row)
        
        st.dataframe(summary_display.style.apply(highlight_summary, axis=1))
    
    st.markdown("---")
    
    # Display calculation logic
    st.subheader("Calculation Logic:")
    st.markdown("""
    - Filtered for MUSIC, PHYS ED, ART, and CREATIVE courses with students > 0
    - Base Student thresholds: 
        - MIXED/1/2/3 = 23 students
        - 4/5 = 26 students
        - KINDER/K = 22 students
    - Overload Pay = Overload Students × ${} × {} weeks
    """.format(pay_rate, number_of_weeks))
    
    st.markdown("---")
    
    # Add download button
    def get_csv_download_link(df, filename):
        csv = df.to_csv(index=False)
        b64 = base64.b64encode(csv.encode()).decode()
        href = f'<a href="data:file/csv;base64,{b64}" download="{filename}">Download CSV</a>'
        return href
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown(get_csv_download_link(results["data"], f"{school_name or 'School'}_All_Courses.csv"), unsafe_allow_html=True)
    with col2:
        st.markdown(get_csv_download_link(results["non_zero_data"], f"{school_name or 'School'}_Overload_Only.csv"), unsafe_allow_html=True)
    
    # Add timestamp
    st.caption(f"Report generated on {datetime.datetime.now().strftime('%Y-%m-%d at %H:%M:%S')}")
