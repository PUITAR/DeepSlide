"""
Test advanced image processing with OpenCV.
"""

import pytest


class TestImageProcessingAdvanced:
    """Test advanced image processing with OpenCV."""

    @pytest.mark.asyncio
    async def test_opencv_complex_processing(
        self, agent_env, workspace, tool_call_helper
    ):
        """Test OpenCV: create image + draw multiple shapes + add text + apply filters."""
        script_content = """
import cv2
import numpy as np

# Create base image
img = np.zeros((400, 600, 3), dtype=np.uint8)
img[:, :] = (255, 255, 255)  # White background

# Draw complex shapes
cv2.rectangle(img, (50, 50), (550, 350), (0, 0, 255), 3)  # Red rectangle
cv2.circle(img, (300, 200), 100, (0, 255, 0), -1)  # Green filled circle
cv2.ellipse(img, (300, 200), (150, 80), 45, 0, 360, (255, 0, 0), 2)  # Blue ellipse
cv2.line(img, (50, 50), (550, 350), (255, 0, 255), 2)  # Magenta line
cv2.line(img, (550, 50), (50, 350), (255, 255, 0), 2)  # Cyan line

# Add text
font = cv2.FONT_HERSHEY_SIMPLEX
cv2.putText(img, 'OpenCV Advanced', (180, 80), font, 1.2, (0, 0, 0), 2, cv2.LINE_AA)
cv2.putText(img, 'Test Image', (220, 320), font, 1, (0, 0, 0), 2, cv2.LINE_AA)

# Draw polygon
pts = np.array([[100, 150], [150, 100], [250, 120], [200, 180]], np.int32)
pts = pts.reshape((-1, 1, 2))
cv2.polylines(img, [pts], True, (0, 128, 255), 2)

# Save original
cv2.imwrite('opencv_original.png', img)

# Apply Gaussian blur
blurred = cv2.GaussianBlur(img, (15, 15), 0)
cv2.imwrite('opencv_blurred.png', blurred)

# Apply edge detection
gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
edges = cv2.Canny(gray, 50, 150)
cv2.imwrite('opencv_edges.png', edges)

print(f'opencv_original.png created ({img.shape[1]}x{img.shape[0]})')
print(f'opencv_blurred.png created')
print(f'opencv_edges.png created')
print(f'OpenCV version: {cv2.__version__}')
"""
        write_call = tool_call_helper(
            "write_file",
            {"path": str(workspace / "test_opencv.py"), "content": script_content},
        )
        await agent_env.tool_execute(write_call)

        exec_call = tool_call_helper(
            "execute_command",
            {"command": f"python {workspace / 'test_opencv.py'}"},
        )
        exec_result = await agent_env.tool_execute(exec_call)
        assert not exec_result.is_error, f"opencv test failed: {exec_result.text}"
        assert "opencv_original.png created" in exec_result.text
        assert "opencv_blurred.png created" in exec_result.text
        assert "opencv_edges.png created" in exec_result.text

        # Verify all three images created
        list_call = tool_call_helper(
            "list_directory",
            {"path": str(workspace)},
        )
        list_result = await agent_env.tool_execute(list_call)
        assert "opencv_original.png" in list_result.text
        assert "opencv_blurred.png" in list_result.text
        assert "opencv_edges.png" in list_result.text
