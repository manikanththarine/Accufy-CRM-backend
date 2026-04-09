const User = require('../models/user.model');
const { generateToken } = require('../utils/auth.util');

const register = async (req, res) => {
  try {
    const { name, email, password, role } = req.body;

    const existingUser = await userService.getUserByEmail(email);
    if (existingUser) {
      return res.status(409).json({ message: 'Email already in use' });
    }

    const createdUser = await userService.createUser({ name, email, password, role });
    const token = generateToken({ id: createdUser._id, email: createdUser.email, role: createdUser.role });

    res.status(201).json({
      user: {
        id: createdUser._id,
        name: createdUser.name,
        email: createdUser.email,
        role: createdUser.role,
      },
      token,
    });
  } catch (error) {
    console.error('register error', error);
    res.status(500).json({ message: 'Server error' });
  }
};

const login = async (req, res) => {

  try {
    const { email, password } = req.body;

    const user = await User.findOne({ email });
    // if (!user) {
    //   return res.status(401).json({ message: 'Invalid credentials' })
    // }

    const isMatch = await user.comparePassword(password);
    // if (!isMatch) {
    //   return res.status(401).json({ message: 'Invalid credentials' });
    // }

      console.log(email + ' ' + password)


    const token = generateToken({ id: user._id, email: user.email, role: user.role });
        console.log(user, token)

    res.json({
      user: {
        id: user._id,
        name: user.name,
        email: user.email,
        role: user.role,
      },
      token,
    });
  } catch (error) {
    console.error('login error', error);
    res.status(500).json({ message: 'Server error' });
  }
};

const profile = async (req, res) => {
  try {
    const user = await userService.getUserById(req.user.id);
    if (!user) return res.status(404).json({ message: 'User not found' });

    res.json({ user });
  } catch (error) {
    console.error('profile error', error);
    res.status(500).json({ message: 'Server error' });
  }
};

module.exports = { register, login, profile };
