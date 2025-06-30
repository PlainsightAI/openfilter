# OpenFilter Heroku Demo

A real-time video processing pipeline that demonstrates OpenFilter's capabilities for multi-stream video processing deployed in Heroku's Fir. This demo creates multiple video streams from a single input source, applies various effects, and provides a web-based visualization interface.

## Features

- **Multi-stream Processing**: Creates multiple video streams from a single input:
  - Main stream (optionally resized)
  - Blurred stream (Gaussian blur)
  - Edge detection stream (Canny edge detection)
  - Overlay stream (with timestamp and frame counter)
- **Web Visualization**:
  - Combined view showing all streams in a grid layout
  - Analytics view with real-time metrics:
    - Frame rate monitoring
    - Brightness analysis
    - Edge density measurements
- **Heroku Support**: Ready to deploy on Heroku with proper configuration
- **Configurable**: Customizable through environment variables and command-line arguments

## Prerequisites

- Python 3.11.9
- OpenFilter library
- Heroku CLI installed and configured to deploy apps [here](https://devcenter.heroku.com/articles/heroku-cli)
- Familiar with Python deployment in Heroku's Fir [here](https://devcenter.heroku.com/articles/getting-started-with-python-fir)

## Environment Variables

The following environment variables can be configured:

- `PORT`: Web server port (required)
- `VIDEO_SOURCE`: Input video source URI (default: `file://./assets/sample-video.mp4!loop`)
- `OUTPUT_FPS`: Output video frame rate (default: 30)
- `OUTPUT_DIR`: Directory for output files (default: `/tmp/output`)
- `MAIN_RESIZE`: Enable/disable main stream resizing (default: "0")

## Filter Configuration

### FrameProcessor Configuration
The `FrameProcessor` filter handles the initial video processing and creates multiple output streams:
- `main_resize`: Enable/disable main stream resizing (default: false)
- `apply_blur`: Enable/disable Gaussian blur effect (default: true)
- `apply_edge_detection`: Enable/disable edge detection (default: true)
- `apply_overlay`: Enable/disable timestamp overlay (default: true)

### FrameVisualizer Configuration
The `FrameVisualizer` filter handles the visualization and analytics of the processed streams:
- `create_combined_view`: Enable/disable combined visualization (default: true)
- `create_analytics`: Enable/disable analytics dashboard (default: true)
- `required_topics`: List of required input topics (default: ["main", "blurred", "edges", "overlay"])

## Installation

1. Clone the repository and navigate to the current folder
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `.env` file with your configuration (optional)

## Heroku login and configurations

To log in to the Heroku CLI, use the heroku login command

```bash
heroku login
```

This command opens your web browser to the Heroku login page. If your browser is already logged in to Heroku, click the Log In button on the page.

Create an app on Heroku to prepare the platform to receive your source code by replacing <space-name> with the name of your Fir space in the command below:

```bash
heroku create --space <space-name>
```

When you create an app, a Git remote called heroku also gets created and associated with your local Git repository. Git remotes are versions of your repository that live on other servers. You deploy your app by pushing its code to that special Heroku-hosted remote associated with your app.

### Setting up Heroku Remote

Since this demo lives in a subdirectory of a larger repository, you need to set up the Heroku remote manually:

```bash
# Add the Heroku remote (replace <your-app-name> with your app name)
git remote add heroku https://git.heroku.com/<your-app-name>.git
```

### Deployment

To deploy the application, use the Makefile command which handles the subtree push:

```bash
make deploy
```

Or manually deploy using git subtree:

```bash
# From the root of the repository
git subtree push --prefix examples/openfilter-heroku-demo heroku main
```

## Development with Makefile

This project uses a Makefile to simplify common development tasks. The Makefile provides several convenient commands:

```bash
# Run the application locally
make run

# Deploy to Heroku
make deploy

# Clean up temporary files
make clean

# Install dependencies
make install

# Help
make help
```

Using the Makefile helps maintain consistency across different development environments and reduces the chance of errors from manual command execution. It also serves as a quick reference for common development tasks.

### Local Development with Heroku Local

You can also run the application locally using Heroku's local development environment, which simulates the Heroku environment on your machine:

```bash
# Install Heroku CLI if you haven't already
brew install heroku/brew/heroku

# Install Heroku CLI on Linux
curl https://cli-assets.heroku.com/install.sh | sh

# Run the application using heroku local
heroku local web
```

This approach ensures that your local development environment closely matches the production environment on Heroku. The application will be available at `http://localhost:5000` by default.

### Procfile Configuration

The project includes a `Procfile` that tells Heroku how to run the application. The Procfile is a simple text file that specifies the commands that should be executed to start your application:

```
web: python app.py
```

This configuration:
- Declares a `web` process type that Heroku will use to handle HTTP traffic
- Specifies the command to start the application (`python app.py`)
- Allows Heroku to automatically detect and run the application
- Works seamlessly with both `heroku local` and production deployment

The Procfile is essential for Heroku deployment as it defines the process types and commands that make up your application. When you run `heroku local`, it uses this same Procfile to start your application locally.

### Application URLs

Once deployed, the application provides several visualization endpoints:

- Main view: `https://<app-name>.herokuapp.com/`
- Edges view: `https://<app-name>.herokuapp.com/edges`
- Blurred view: `https://<app-name>.herokuapp.com/blurred`
- Overlay view: `https://<app-name>.herokuapp.com/overlay`
- Analytics view: `https://<app-name>.herokuapp.com/analytics`

To find your app name you can run `heroku open` within the folder you've made the deployment or

1. After creating your Heroku app, you can find its name in the Heroku dashboard
2. Or use the Heroku CLI:
   ```bash
   heroku apps
   ```
3. The app name will be in the format `your-app-name.herokuapp.com`

Replace `<app-name>` in the URLs above with your actual Heroku app name to access the different visualization views.

## Usage

### Local Development

Run the application locally:

```bash
python app.py --input <video_source> --fps <frame_rate>
```

### Heroku Deployment

1. Create a new Heroku app

2. Deploy the application:
   ```bash
   git push heroku main

   or

   make deploy
   ```

## Pipeline Architecture

The application uses a pipeline of filters:

1. **VideoIn**: Handles input video source
2. **FrameProcessor**: Creates multiple output streams with different effects
3. **FrameVisualizer**: Processes and combines the streams with analytics
4. **Webvis**: Provides web-based visualization

```
┌─────────────┐     ┌─────────────────┐     ┌─────────────────┐     ┌─────────────┐
│   VideoIn   │     │ FrameProcessor  │     │ FrameVisualizer │     │   Webvis    │
│             │     │                 │     │                 │     │             │
│ Input Video ├────►│ - Main Stream   ├────►│ - Combined View ├────►│ Web Browser │
│             │     │ - Blurred       │     │ - Analytics     │     │             │
│             │     │ - Edge Detection│     │ - Metrics       │     │             │
│             │     │ - Overlay       │     │                 │     │             │
└─────────────┘     └─────────────────┘     └─────────────────┘     └─────────────┘
                           │                         │
                           │                         │
                           ▼                         ▼
                    ┌─────────────────┐     ┌─────────────────┐
                    │ Output Streams  │     │ Analytics Data  │
                    │ - Main          │     │ - FPS           │
                    │ - Blurred       │     │ - Brightness    │
                    │ - Edges         │     │ - Edge Density  │
                    │ - Overlay       │     │                 │
                    └─────────────────┘     └─────────────────┘
```

The diagram above shows the flow of data through the pipeline:
1. Video input is captured by VideoIn
2. FrameProcessor creates multiple processed streams
3. FrameVisualizer combines streams and generates analytics
4. Webvis serves the results to web browsers
5. Additional outputs are available as separate streams and analytics data

## Output

The pipeline generates:
- Web interface for real-time stream visualization

# Other resources:

[Getting Started on Heroku Fir with Python](https://devcenter.heroku.com/articles/getting-started-with-python-fir#create-your-app-in-a-fir-space)
