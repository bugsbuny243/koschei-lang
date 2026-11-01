// Koschei Core Library: platform_ai
// Pure model-request admission: no model weights, inference, tools or I/O.
// Output tokens are a declared request budget, NOT tokenizer enforcement.
fn admit(model: String, allowed_models: List<String>, input_bytes: Int, input_limit: Int, output_token_limit: Int) -> Result<String, Error> {
    if model.length() == 0 || model.length() > 64 ||
       allowed_models.length() == 0 || allowed_models.length() > 64 ||
       !allowed_models.contains(model) {
        return Err(Error("platform_ai: model is not allowlisted"))
    }
    if input_limit < 1 || input_limit > 1048576 ||
       input_bytes < 1 || input_bytes > input_limit ||
       output_token_limit < 1 || output_token_limit > 8192 {
        return Err(Error("platform_ai: request budget exceeded"))
    }
    return Ok(model)
}
fn batch_allowed(count: Int, maximum: Int) -> Bool {
    return count > 0 && maximum > 0 && maximum <= 128 && count <= maximum
}
