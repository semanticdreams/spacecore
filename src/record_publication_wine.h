#pragma once

#include "record_publication.h"

namespace record_publication::wine {

bool detected();
void initialize_process_environment();
Result publish(const std::filesystem::path& destination, std::string_view payload, const Hooks& hooks);

} // namespace record_publication::wine
