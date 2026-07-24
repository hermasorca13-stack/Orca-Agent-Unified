const Joi = require('joi');

const validateRequest = (schema) => {
  return (req, res, next) => {
    const { error, value } = schema.validate(req.body, {
      abortEarly: false,
      stripUnknown: true
    });

    if (error) {
      const messages = error.details.map(detail => ({
        field: detail.path.join('.'),
        message: detail.message
      }));

      return res.status(400).json({
        error: 'Validation failed',
        details: messages
      });
    }

    req.body = value;
    next();
  };
};

const syncSchema = Joi.object({
  repositories: Joi.boolean().default(true),
  issues: Joi.boolean().default(true),
  pullRequests: Joi.boolean().default(true),
  force: Joi.boolean().default(false)
});

module.exports = {
  validateRequest,
  syncSchema
};
