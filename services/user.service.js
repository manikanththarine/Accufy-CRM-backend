const User = require('../models/user.model');

const createUser = async ({ name, email, password, role }) => {
  const user = new User({ name, email, password, role });
  return user.save();
};

const getUserByEmail = async (email) => User.findOne({ email });

const getUserById = async (id) => User.findById(id).select('-password');

const validateCredentials = async (email, password) => {
  const user = await getUserByEmail(email);
  if (!user) return null;

  const isMatch = await user.comparePassword(password);
  if (!isMatch) return null;

  return user;
};

module.exports = {
  createUser,
  getUserByEmail,
  getUserById,
  validateCredentials,
};
