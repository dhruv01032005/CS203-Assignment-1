# importing the required modules that are necessary
import json
import os
import logging
from flask import Flask, render_template, request, redirect, url_for, flash
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.trace import StatusCode

# Setting up the Flask application
app = Flask(__name__)
app.secret_key = 'secret'  # Used for session management (e.g., flash messages)
COURSE_FILE = 'course_catalog.json'  # JSON file where course details are stored(course_catlog.json)

# Configuring logging to track application events and errors
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', 
    datefmt='%Y-%m-%d %H:%M:%S' #standard format
)

# OpenTelemetry setup for distributed tracing
resource = Resource.create({"service.name": "course-catalog-service"})
# Service identifier
# Setting the tracer provider with a specific resource to identify the service in tracing data.
trace.set_tracer_provider(TracerProvider(resource=resource))
tracer = trace.get_tracer(__name__)  # Tracer for this script

# Setting up Jaeger exporter for distributed trace collection
jaeger_exporter = JaegerExporter(
    agent_host_name="localhost",  # Host where Jaeger is running
    agent_port=6831  # Default port for Jaeger UDP(User Datagram Protocol)
)

# Adding span processor for Jaeger
# Configuring a batch span processor to handle spans and export them to the Jaeger exporter.
span_processor = BatchSpanProcessor(jaeger_exporter) 
# Adding the configured span processor (Jaeger exporter) to the tracer provider.
trace.get_tracer_provider().add_span_processor(span_processor) 

# Instrumenting the Flask app to collect telemetry data for all incoming requests.
FlaskInstrumentor().instrument_app(app)

# Adding a console exporter for local debugging of spans
console_exporter = ConsoleSpanExporter()
span_processor_2 = BatchSpanProcessor(console_exporter)
# Adding the console span processor to the tracer provider to enable console logging of trace data.
trace.get_tracer_provider().add_span_processor(span_processor_2)

# Helper function to load courses from the JSON file
def load_courses():
    """Loads courses from the JSON file. Returns an empty list if the file doesn't exist."""
    if not os.path.exists(COURSE_FILE):  # Checking if the file exists
        return []
    with open(COURSE_FILE, 'r') as file:
        return json.load(file)  # Reading and parsing the JSON file


# Helper function to save a new course into the JSON file
def save_courses(data):
    """Saves new course data into the JSON file."""
    courses = load_courses()  # Loading existing courses first
    courses.append(data)  # Adding the new course to the list
    with open(COURSE_FILE, 'w') as file:
        json.dump(courses, file, indent=4)  # Writing the updated list back to the file


# Route for the homepage
@app.route('/')
def index():
    with tracer.start_as_current_span("index_route") as span:
        # Tracing user details(user ip) and HTTP status
        span.set_attribute("user.ip", request.remote_addr)
        span.set_attribute("http.method", request.method)
        span.set_attribute("http.status_code", 200)
        return render_template('index.html')  # Render the homepage


# Route for displaying the course catalog
@app.route('/catalog')
def course_catalog():
    with tracer.start_as_current_span("course_catalog_route") as span:
        # Tracing the number of courses
        span.set_attribute("user.ip", request.remote_addr)
        courses = load_courses()  # Loading all courses
        span.set_attribute("courses.count", len(courses))  # Adding course count to span
        span.set_attribute("http.status_code", 200)
        return render_template('course_catalog.html', courses=courses)


# Route to add a new course (GET: form page, POST: handle submission)
@app.route('/add_course', methods=['GET', 'POST'])
def add_course():
    with tracer.start_as_current_span("add_course_route") as span:
        if request.method == 'POST':  # Handling form submission
            # Extract form data
            course_name = request.form.get('name', '').strip()
            instructor = request.form.get('instructor', '').strip()
            semester = request.form.get('semester', '').strip()

            # Validating inputs
            if not course_name or not instructor:
                span.set_status(StatusCode.ERROR, description="Validation failed")
                flash("Course name and instructor are required!", "error")  # Showing error message
                return render_template('add_course.html')

            # Generateing a unique course code for every course
            # We have generated this code because if we click on that preadded course (so by code) it wil load the details of that specific added course
            new_code = course_name[:4].upper() + str(len(load_courses()) + 1)
            course = {
                "code": new_code,
                "name": course_name,
                "instructor": instructor,
                "semester": semester,
            }

            # Saving the new course and updating tracing span
            span.set_attribute("course.data", json.dumps(course))
            span.set_attribute("code",code)
            span.set_attribute("course name",course_name)
            span.set_attribute("instructor",instructor)
            span.set_attribute("semester",semester)
            save_courses(course)
            span.set_status(StatusCode.OK)# Indicating that the span has completed successfully without errors.
            flash(f"Course '{course['name']}' added successfully!", "success")  # Showing success message after adding the course
            return redirect(url_for('course_catalog'))

        span.set_attribute("http.status_code", 200)
        return render_template('add_course.html')  # Showing the course creation form


# Route to view details of a specific course
@app.route('/course/<code>')
def course_details(code):
    with tracer.start_as_current_span(f"course_details_route:{code}") as span:
        courses = load_courses()  # Load all courses
        # Find the course matching the given code
        course = next((course for course in courses if course['code'] == code), None)

        if not course:  # Handling the case when the course is not found
            span.set_status(StatusCode.ERROR, description="Course not found")
            span.set_attribute("http.status_code", 404)
            logging.error(f"Course with code '{code}' not found.")
            # Showing error message  
            flash(f"No course found with code '{code}'.", "error")
            return redirect(url_for('course_catalog'))
         # Rendering course details
        return render_template('course_details.html', course=course) 


# Starting the Flask application
if __name__ == '__main__':
    app.run(debug=True, port=8000)  # Running in debug mode for development
