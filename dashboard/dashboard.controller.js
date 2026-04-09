const getDashboard = async (req, res) => {
  try {
    res.json({
      message: 'Dashboard data',
      user: req.user || null,
      stats: {
        users: 0,
        active: 0,
      },
    });
  } catch (error) {
    console.error('dashboard error', error);
    res.status(500).json({ message: 'Server error' });
  }
};

module.exports = { getDashboard };
