from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import numpy as np
import six
import tensorflow as tf

from edward.util import logit, get_dims, get_session


def evaluate(metrics, latent_vars, data, y_true=None, model_wrapper=None, n_samples=100):
    """Evaluate fitted model using a set of metrics.

    Parameters
    ----------
    metrics : list or str
        List of metrics or a single metric.
    latent_vars : dict of RandomVaribale to RandomVariable
        Collection of random variables binded to their approximate
        posterior.
    data : dict
        Data to evaluate model with. It binds observed variables (of
        type `RandomVariable`) to their realizations (of type
        `tf.Tensor` or `np.ndarray`). It can also bind placeholders
        (of type `tf.Tensor`) used in the model to their realizations.
    y_true : np.ndarray or tf.Tensor
        True values to compare to in supervised learning tasks.
    model_wrapper : ed.Model, optional
        An optional wrapper for the probability model. It must have a
        `predict()` method. If specified, the random variables in
        `latent_vars`' dictionary keys are strings used accordingly by
        the wrapper. `data` is also changed. For TensorFlow, Python,
        and Stan models, the key type is a string; for PyMC3, the key
        type is a Theano shared variable. For TensorFlow, Python, and
        PyMC3 models, the value type is a NumPy array or TensorFlow
        placeholder; for Stan, the value type is the type according to
        the Stan program's data block.
    n_samples : int, optional
        Number of posterior samples for making predictions,
        using the posterior predictive distribution.

    Returns
    -------
    list or float
        A list of evaluations or a single evaluation.

    Raises
    ------
    NotImplementedError
        If an input metric does not match an implemented metric in Edward.
    """
    sess = get_session()
    # Monte Carlo estimate the mean of the posterior predictive:
    # 1. Sample a batch of latent variables from posterior
    zs = {key: rv.sample(n_samples) for key, rv in six.iteritems(latent_vars)}
    # 2. Make predictions, averaging over each sample of latent variables
    y_pred = model_wrapper.predict(data, zs)

    # Evaluate y_pred according to y_true for all metrics.
    evaluations = []
    if isinstance(metrics, str):
        metrics = [metrics]

    for metric in metrics:
        if metric == 'accuracy' or metric == 'crossentropy':
            # automate binary or sparse cat depending on max(y_true)
            support = tf.reduce_max(y_true).eval()
            if support <= 1:
                metric = 'binary_' + metric
            else:
                metric = 'sparse_categorical_' + metric

        if metric == 'binary_accuracy':
            evaluations += [sess.run(binary_accuracy(y_true, y_pred))]
        elif metric == 'categorical_accuracy':
            evaluations += [sess.run(categorical_accuracy(y_true, y_pred))]
        elif metric == 'sparse_categorical_accuracy':
            evaluations += [sess.run(sparse_categorical_accuracy(y_true, y_pred))]
        elif metric == 'log_loss' or metric == 'binary_crossentropy':
            evaluations += [sess.run(binary_crossentropy(y_true, y_pred))]
        elif metric == 'categorical_crossentropy':
            evaluations += [sess.run(categorical_crossentropy(y_true, y_pred))]
        elif metric == 'sparse_categorical_crossentropy':
            evaluations += [sess.run(sparse_categorical_crossentropy(y_true, y_pred))]
        elif metric == 'hinge':
            evaluations += [sess.run(hinge(y_true, y_pred))]
        elif metric == 'squared_hinge':
            evaluations += [sess.run(squared_hinge(y_true, y_pred))]
        elif metric == 'mse' or metric == 'MSE' or \
             metric == 'mean_squared_error':
            evaluations += [sess.run(mean_squared_error(y_true, y_pred))]
        elif metric == 'mae' or metric == 'MAE' or \
             metric == 'mean_absolute_error':
            evaluations += [sess.run(mean_absolute_error(y_true, y_pred))]
        elif metric == 'mape' or metric == 'MAPE' or \
             metric == 'mean_absolute_percentage_error':
            evaluations += [sess.run(mean_absolute_percentage_error(y_true, y_pred))]
        elif metric == 'msle' or metric == 'MSLE' or \
             metric == 'mean_squared_logarithmic_error':
            evaluations += [sess.run(mean_squared_logarithmic_error(y_true, y_pred))]
        elif metric == 'poisson':
            evaluations += [sess.run(poisson(y_true, y_pred))]
        elif metric == 'cosine' or metric == 'cosine_proximity':
            evaluations += [sess.run(cosine_proximity(y_true, y_pred))]
        elif metric == 'log_lik' or metric == 'log_likelihood':
            evaluations += [sess.run(y_pred)]
        else:
            raise NotImplementedError()

    if len(evaluations) == 1:
        return evaluations[0]
    else:
        return evaluations


def ppc(latent_vars, data=None, T=None, model_wrapper=None, n_samples=100):
    """Posterior predictive check.
    (Rubin, 1984; Meng, 1994; Gelman, Meng, and Stern, 1996)
    If no posterior approximation is provided through ``variational``,
    then we default to a prior predictive check (Box, 1980).

    PPC's form an empirical distribution for the predictive discrepancy,

    .. math::
        p(T) = \int p(T(xrep) | z) p(z | x) dz

    by drawing replicated data sets xrep and calculating
    :math:`T(xrep)` for each data set. Then it compares it to
    :math:`T(x)`.

    Parameters
    ----------
    latent_vars : list of RandomVariable or dict of RandomVariable to RandomVariable
        Collection of random variables. If dictionary, they are binded
        to their approximate posterior. If list, they are not binded
        to anything, and samples are instead obtained from the prior.
    data : dict, optional
        Data to compare to. It binds observed variables (of type
        `RandomVariable`) to their realizations (of type `tf.Tensor`
        or `np.ndarray`). It can also bind placeholders (of type
        `tf.Tensor`) used in the model to their realizations. If not
        specified, will return only the reference distribution with an
        assumed replicated data set size of 1.
    model_wrapper : ed.Model, optional
        An optional wrapper for the probability model. It must have a
        ``sample_likelihood`` method. If `latent_vars` is a list
        (i.e., a prior predictive check), it must also have a
        ``sample_prior`` method. If specified, the random variables in
        `latent_vars`' list or dictionary keys are strings used
        accordingly by the wrapper. `data` is also changed.  For
        TensorFlow, Python, and Stan models, the key type is a string;
        for PyMC3, the key type is a Theano shared variable. For
        TensorFlow, Python, and PyMC3 models, the value type is a
        NumPy array or TensorFlow placeholder; for Stan, the value
        type is the type according to the Stan program's data block.
    T : function, optional
        Discrepancy function, which takes a data dictionary and list
        of latent variables as input and outputs a tf.Tensor. Default
        is the identity function.
    n_samples : int, optional
        Number of replicated data sets.

    Returns
    -------
    list
        List containing the reference distribution, which is a Numpy
        vector of size elements,

        .. math::
            (T(xrep^{1}, z^{1}), ..., T(xrep^{size}, z^{size}))

        and the realized discrepancy, which is a NumPy vector of size
        elements,

        .. math::
            (T(x, z^{1}), ..., T(x, z^{size})).

        If the discrepancy function is not specified, then the list
        contains the full data distribution where each element is a
        data set (dictionary).
    """
    sess = get_session()
    if data is None:
        N = 1
        x = {}
    else:
        # Assume all values have the same data set size.
        N = get_dims(list(six.itervalues(data))[0])[0]
        x = data

    # 1. Sample from posterior (or prior).
    # We fetch zs out of the session because sample_likelihood() may
    # require a SciPy-based sampler.
    if isinstance(latent_vars, dict):
        # `tf.identity()` is to avoid fetching, e.g., a placeholder x
        # when feeding the dictionary {x: np.array()}. TensorFlow will
        # raise an error.
        zs = {key: tf.identity(rv.sample(n_samples))
              for key, rv in six.iteritems(latent_vars)}
        zs = sess.run(zs)
    else:
        zs = model_wrapper.sample_prior(n_samples)
        zs = sess.run(zs)

    # 2. Sample from likelihood.
    xreps = model_wrapper.sample_likelihood(zs, N)

    # 3. Calculate discrepancy.
    if T is None:
        if x is None:
            return xreps
        else:
            return [xreps, y]

    Txreps = []
    Txs = []
    zs_unpacked = {key: tf.unpack(z_samples)
                   for key, z_samples in six.iteritems(zs)}
    for n, xrep in enumerate(xreps):
        z = {key: z_samples[n]
             for key, z_samples in six.iteritems(zs_unpacked)}
        Txreps += [T(xrep, z)]
        if x is not None:
            Txs += [T(x, z)]

    if x is None:
        return sess.run(tf.pack(Txreps))
    else:
        return sess.run([tf.pack(Txreps), tf.pack(Txs)])


# Classification metrics


def binary_accuracy(y_true, y_pred):
    """Binary prediction accuracy, also known as 0/1-loss.

    Parameters
    ----------
    y_true : tf.Tensor
        Tensor of 0s and 1s.
    y_pred : tf.Tensor
        Tensor of probabilities.
    """
    y_true = tf.cast(y_true, tf.float32)
    y_pred = tf.cast(tf.round(y_pred), tf.float32)
    return tf.reduce_mean(tf.cast(tf.equal(y_true, y_pred), tf.float32))


def categorical_accuracy(y_true, y_pred):
    """Multi-class prediction accuracy. One-hot representation for ``y_true``.

    Parameters
    ----------
    y_true : tf.Tensor
        Tensor of 0s and 1s, where the outermost dimension of size ``K``
        has only one 1 per row.
    y_pred : tf.Tensor
        Tensor of probabilities, with same shape as ``y_true``.
        The outermost dimension denote the categorical probabilities for
        that data point per row.
    """
    y_true = tf.cast(tf.argmax(y_true, len(y_true.get_shape()) - 1), tf.float32)
    y_pred = tf.cast(tf.argmax(y_pred, len(y_pred.get_shape()) - 1), tf.float32)
    return tf.reduce_mean(tf.cast(tf.equal(y_true, y_pred), tf.float32))


def sparse_categorical_accuracy(y_true, y_pred):
    """Multi-class prediction accuracy. Label {0, 1, .., K-1}
    representation for ``y_true``.

    Parameters
    ----------
    y_true : tf.Tensor
        Tensor of integers {0, 1, ..., K-1}.
    y_pred : tf.Tensor
        Tensor of probabilities, with shape ``(y_true.get_shape(), K)``.
        The outermost dimension are the categorical probabilities for
        that data point.
    """
    y_true = tf.cast(y_true, tf.float32)
    y_pred = tf.cast(tf.argmax(y_pred, len(y_pred.get_shape()) - 1), tf.float32)
    return tf.reduce_mean(tf.cast(tf.equal(y_true, y_pred), tf.float32))


def binary_crossentropy(y_true, y_pred):
    """Binary cross-entropy.

    Parameters
    ----------
    y_true : tf.Tensor
        Tensor of 0s and 1s.
    y_pred : tf.Tensor
        Tensor of probabilities.
    """
    y_true = tf.cast(y_true, tf.float32)
    y_pred = logit(tf.cast(y_pred, tf.float32))
    return tf.reduce_mean(tf.nn.sigmoid_cross_entropy_with_logits(y_pred, y_true))


def categorical_crossentropy(y_true, y_pred):
    """Multi-class cross entropy. One-hot representation for ``y_true``.

    Parameters
    ----------
    y_true : tf.Tensor
        Tensor of 0s and 1s, where the outermost dimension of size K
        has only one 1 per row.
    y_pred : tf.Tensor
        Tensor of probabilities, with same shape as y_true.
        The outermost dimension denote the categorical probabilities for
        that data point per row.
    """
    y_true = tf.cast(y_true, tf.float32)
    y_pred = logit(tf.cast(y_pred, tf.float32))
    return tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(y_pred, y_true))


def sparse_categorical_crossentropy(y_true, y_pred):
    """Multi-class cross entropy. Label {0, 1, .., K-1} representation
    for ``y_true.``

    Parameters
    ----------
    y_true : tf.Tensor
        Tensor of integers {0, 1, ..., K-1}.
    y_pred : tf.Tensor
        Tensor of probabilities, with shape ``(y_true.get_shape(), K)``.
        The outermost dimension are the categorical probabilities for
        that data point.
    """
    y_true = tf.cast(y_true, tf.int64)
    y_pred = logit(tf.cast(y_pred, tf.float32))
    return tf.reduce_mean(tf.nn.sparse_softmax_cross_entropy_with_logits(y_pred, y_true))


def hinge(y_true, y_pred):
    """Hinge loss.

    Parameters
    ----------
    y_true : tf.Tensor
        Tensor of 0s and 1s.
    y_pred : tf.Tensor
        Tensor of real value.
    """
    y_true = tf.cast(y_true, tf.float32)
    y_pred = tf.cast(y_pred, tf.float32)
    return tf.reduce_mean(tf.maximum(1.0 - y_true * y_pred, 0.0))


def squared_hinge(y_true, y_pred):
    """Squared hinge loss.

    Parameters
    ----------
    y_true : tf.Tensor
        Tensor of 0s and 1s.
    y_pred : tf.Tensor
        Tensor of real value.
    """
    y_true = tf.cast(y_true, tf.float32)
    y_pred = tf.cast(y_pred, tf.float32)
    return tf.reduce_mean(tf.square(tf.maximum(1.0 - y_true * y_pred, 0.0)))


# Regression metrics


def mean_squared_error(y_true, y_pred):
    """Mean squared error loss.

    Parameters
    ----------
    y_true : tf.Tensor
    y_pred : tf.Tensor
        Tensors of same shape and type.
    """
    return tf.reduce_mean(tf.square(y_pred - y_true))


def mean_absolute_error(y_true, y_pred):
    """Mean absolute error loss.

    Parameters
    ----------
    y_true : tf.Tensor
    y_pred : tf.Tensor
        Tensors of same shape and type.
    """
    return tf.reduce_mean(tf.abs(y_pred - y_true))


def mean_absolute_percentage_error(y_true, y_pred):
    """Mean absolute percentage error loss.

    Parameters
    ----------
    y_true : tf.Tensor
    y_pred : tf.Tensor
        Tensors of same shape and type.
    """
    diff = tf.abs((y_true - y_pred) / tf.clip_by_value(tf.abs(y_true), 1e-8, np.inf))
    return 100.0 * tf.reduce_mean(diff)


def mean_squared_logarithmic_error(y_true, y_pred):
    """Mean squared logarithmic error loss.

    Parameters
    ----------
    y_true : tf.Tensor
    y_pred : tf.Tensor
        Tensors of same shape and type.
    """
    first_log = tf.log(tf.clip_by_value(y_pred, 1e-8, np.inf) + 1.0)
    second_log = tf.log(tf.clip_by_value(y_true, 1e-8, np.inf) + 1.0)
    return tf.reduce_mean(tf.square(first_log - second_log))


def poisson(y_true, y_pred):
    """Negative Poisson log-likelihood of data ``y_true`` given predictions
    ``y_pred`` (up to proportion).

    Parameters
    ----------
    y_true : tf.Tensor
    y_pred : tf.Tensor
        Tensors of same shape and type.
    """
    return tf.reduce_sum(y_pred - y_true * tf.log(y_pred + 1e-8))


def cosine_proximity(y_true, y_pred):
    """Cosine similarity of two vectors.

    Parameters
    ----------
    y_true : tf.Tensor
    y_pred : tf.Tensor
        Tensors of same shape and type.
    """
    y_true = tf.nn.l2_normalize(y_true, len(y_true.get_shape()) - 1)
    y_pred = tf.nn.l2_normalize(y_pred, len(y_pred.get_shape()) - 1)
    return tf.reduce_sum(y_true * y_pred)
