from scipy.interpolate import UnivariateSpline, splprep, splev
import numpy as np

def curvature_splines(x, y, error=0.1, periodic=False):
    """Calculate the signed curvature of a 2D curve at each point
    using interpolating splines.
    Parameters
    ----------
    x,y: numpy.array(dtype=float) shape (n_points, )
         or
         y=None and
         x is a numpy.array(dtype=complex) shape (n_points, )
         In the second case the curve is represented as a np.array
         of complex numbers.
    error : float
        The admisible error when interpolating the splines
    periodic : bool
        Fit a closed periodic curve. Use this for racing lines so the first
        and second derivatives remain continuous across start/finish.
    Returns
    -------
    curvature: numpy.array shape (n_points, )
    Note: This is 2-3x slower (1.8 ms for 2000 points) than `curvature_gradient`
    but more accurate, especially at the borders.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    if x.ndim != 1 or y.ndim != 1 or x.shape != y.shape:
        raise ValueError("x and y must be one-dimensional arrays of equal length")
    if len(x) < 4:
        raise ValueError("at least four points are required to calculate curvature")

    if periodic:
        # Fit the racing line as a genuinely closed curve.  Fitting x and y as
        # two independent, open splines makes their derivatives disagree at
        # the start/finish seam, which produces an artificial curvature sign
        # change in the policy's look-ahead observation.
        duplicate_endpoint = np.hypot(x[-1] - x[0], y[-1] - y[0]) < 1e-9
        fit_x = x[:-1] if duplicate_endpoint else x
        fit_y = y[:-1] if duplicate_endpoint else y

        segment_lengths = np.hypot(np.diff(fit_x), np.diff(fit_y))
        closing_length = np.hypot(fit_x[0] - fit_x[-1], fit_y[0] - fit_y[-1])
        closed_length = segment_lengths.sum() + closing_length
        if closed_length <= 0 or np.any(segment_lengths <= 0) or closing_length <= 0:
            raise ValueError("periodic curvature requires distinct, ordered points")

        arc_distance = np.concatenate(
            ([0.0], np.cumsum(segment_lengths), [closed_length])
        )
        parameter = arc_distance / closed_length
        closed_x = np.concatenate((fit_x, [fit_x[0]]))
        closed_y = np.concatenate((fit_y, [fit_y[0]]))

        # FITPACK's smoothing value is a sum of squared residuals.  Scaling it
        # by the point count preserves the meaning of the existing per-point
        # error parameter while avoiding noisy second derivatives.
        smoothing = len(closed_x) * error ** 2
        spline, _ = splprep(
            [closed_x, closed_y],
            u=parameter,
            k=3,
            s=smoothing,
            per=True,
        )
        evaluation_parameter = parameter[:-1]
        dx, dy = splev(evaluation_parameter, spline, der=1)
        ddx, ddy = splev(evaluation_parameter, spline, der=2)
        dx = np.asarray(dx)
        dy = np.asarray(dy)
        ddx = np.asarray(ddx)
        ddy = np.asarray(ddy)
        denominator = np.power(dx ** 2 + dy ** 2, 3 / 2)
        curvature = (dx * ddy - dy * ddx) / denominator

        if duplicate_endpoint:
            curvature = np.concatenate((curvature, [curvature[0]]))
        return curvature

    t = np.arange(x.shape[0])
    std = error * np.ones_like(x)

    fx = UnivariateSpline(t, x, k=4, w=1 / np.sqrt(std))
    fy = UnivariateSpline(t, y, k=4, w=1 / np.sqrt(std))

    xˈ = fx.derivative(1)(t)
    xˈˈ = fx.derivative(2)(t)
    yˈ = fy.derivative(1)(t)
    yˈˈ = fy.derivative(2)(t)
    curvature = (xˈ* yˈˈ - yˈ* xˈˈ) / np.power(xˈ** 2 + yˈ** 2, 3 / 2)
    return curvature
